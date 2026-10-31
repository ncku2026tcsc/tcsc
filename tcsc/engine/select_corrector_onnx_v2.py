# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import math

from . import ghostveto, phonetics, pronoun, reading_filter, wordphon
from .onnx_engine import log_softmax
from .segmenter import _span_reading_words
from .select_corrector_onnx import OnnxCorrector
from .. import config, settings


class OnnxCorrectorV2(OnnxCorrector):
    def __init__(self, *args, reading_ratio=None, guard_particles=False,
                 lambda_corpus=0.15, lambda_learned=1.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.reading_ratio = reading_ratio
        self.guard_particles = guard_particles
        self.lambda_corpus = lambda_corpus
        self.lambda_learned = lambda_learned

    def _lc(self):
        return self.lambda_corpus if settings.get("corpus_prior", True) else 0.0

    def _same_sound(self, a, b):
        if self.reading_ratio is None:
            return phonetics.same_sound(a, b)
        return reading_filter.same_sound(a, b, self.reading_ratio)

    def _homophone_ok(self, src, cand, word_level=False):
        if len(src) != len(cand):
            return False
        if not word_level:
            return all(self._same_sound(a, b) for a, b in zip(src, cand) if a != b)
        return all(bool(set(phonetics.raw_readings(a)) & set(phonetics.raw_readings(b)))
                   for a, b in zip(src, cand) if a != b)

    def _det_pairs(self, clause):
        c = getattr(self, "_det_cache", None)
        if c is not None and c[0] == clause:
            return c[1]
        try:
            from . import detprop
            pairs = list(detprop.suspects(clause))
        except Exception:
            pairs = []
        self._det_cache = (clause, pairs)
        return pairs

    def _det_unlock(self, clause):
        th = config.ENGINE.get("word_escape_unlock_th", 0.9)
        return {k for k, p in self._det_pairs(clause) if p >= th}

    def _candidates_by_span(self, clause):
        by = {}
        n = len(clause)
        sus = self._det_unlock(clause)
        for L in range(2, self.max_word_len + 1):
            for i in range(0, n - L + 1):
                span = clause[i:i + L]
                full = _span_reading_words(span, unlock={k - i for k in sus if i <= k < i + L})
                ws = [w for w in full[:self.word_cand]
                      if w != span and self._homophone_ok(span, w, word_level=True)]
                ws += [w for w in full
                       if w != span and len(w) == len(span)
                       and w in wordphon._userforce_freq and w not in ws]
                if ws:
                    by[(i, L)] = list(dict.fromkeys(ws))
        for i, ch in enumerate(clause):
            if self.guard_particles and reading_filter.is_guarded_particle(clause, i):
                continue
            cs = [c for c in phonetics.homophones(ch, limit=self.char_cand)
                  if (self._freq(c) >= self.min_cand_freq
                      or (phonetics.extra_readings(c) & phonetics.readings(ch)))
                  and self._same_sound(ch, c)]
            cs += [w for w in wordphon._userforce_freq
                   if len(w) == 1 and w != ch and w not in cs
                   and phonetics.same_sound(ch, w)]
            if ch in self._PRON_GUARD:
                cs = [x for x in cs if x not in self._PRON_GUARD]
            if cs:
                by[(i, 1)] = list(dict.fromkeys(cs))
        return by

    STEP = 1.4
    JMARGIN = 1.0
    OOV_FLOOR = -10.0
    _PRON_GUARD = frozenset("他她它牠祂你妳")

    @staticmethod
    def _prop_top():
        try:
            return max(1, int(settings.get("prop_top") or 3))
        except Exception:
            return 3

    @staticmethod
    def _prop_perslot():
        try:
            return max(0, int(settings.get("prop_perslot") or 0))
        except Exception:
            return 0

    @staticmethod
    def _prop_gain():
        try:
            v = settings.get("prop_gain")
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _prop_cap():
        try:
            return max(1, int(settings.get("prop_cap") or 8))
        except Exception:
            return 8

    @staticmethod
    def _steps(lv):
        if lv and settings.get("f7_direct", True):
            return lv - 1
        return lv

    def _cover_levels(self, clause):
        cov = [0] * len(clause)
        for w, lv in wordphon.defense_levels().items():
            lv = self._steps(lv)
            st = clause.find(w)
            while st != -1:
                for k in range(st, st + len(w)):
                    if lv > cov[k]:
                        cov[k] = lv
                st = clause.find(w, st + 1)
        return cov

    _LPS_CACHE_MAX = 512

    def _lps_store(self):
        cache = getattr(self, "_lps_cache", None)
        if cache is None:
            import collections
            cache = self._lps_cache = collections.OrderedDict()
        return cache

    def _prefetch_lps(self, items):
        cache = self._lps_store()
        todo, seen = [], set()
        for masked, i, L in items:
            key = (tuple(masked), i, L)
            if key not in cache and key not in seen:
                seen.add(key)
                todo.append((key, masked, i, L))
        if len(todo) < 2 or not hasattr(self.bert, "run_singles"):
            return
        outs = self.bert.run_singles([m for _k, m, _i, _L in todo])
        for (key, _m, i, L), logits in zip(todo, outs):
            cache[key] = [log_softmax(logits[p + 1]) for p in range(i, i + L)]
            if len(cache) > self._LPS_CACHE_MAX:
                cache.popitem(last=False)

    def _span_lps(self, masked, i, L):
        cache = self._lps_store()
        key = (tuple(masked), i, L)
        hit = cache.get(key)
        if hit is not None:
            cache.move_to_end(key)
            return hit
        logits = self.bert.run([masked])[0]
        lps = [log_softmax(logits[p + 1]) for p in range(i, i + L)]
        cache[key] = lps
        if len(cache) > self._LPS_CACHE_MAX:
            cache.popitem(last=False)
        return lps

    def _score(self, clause, anchor=None):
        anc = anchor if anchor is not None else clause
        ids = self.bert.encode(clause)
        cov = self._cover_levels(clause)
        fbm = settings.get("frame_prior") or "off"
        gvon = bool(settings.get("ghost_veto"))
        results = []
        spans = []
        for (i, L), words in self._candidates_by_span(anc).items():
            masked = ids[:]
            for p in range(i, i + L):
                masked[p + 1] = self.bert.mask
            spans.append(((i, L), words, masked))
        self._prefetch_lps([(m, i, L) for (i, L), _w, m in spans])
        for (i, L), words, masked in spans:
            lps = self._span_lps(masked, i, L)
            src = clause[i:i + L]
            osp = anc[i:i + L]
            if osp != src and osp not in words:
                words = list(words) + [osp]

            def span_score(word, unk_floor=False):
                s = 0.0
                for k, ch in enumerate(word):
                    tid = self.bert.token_id(ch)
                    if tid is None:
                        if not unk_floor:
                            return None
                        s += self.OOV_FLOOR
                        continue
                    s += float(lps[k][tid])
                return s

            orig = span_score(src, unk_floor=True)
            for w in words:
                sc = span_score(w)
                if sc is None:
                    continue
                cpr = (math.log(1 + wordphon.corpus_freq(w))
                       - math.log(1 + wordphon.corpus_freq(src)))
                atk = self.STEP * self._steps(wordphon.learned_level(w))
                if L >= 2:
                    for k in range(L):
                        if src[k] != w[k]:
                            atk += self.STEP * self._steps(wordphon.learned_level(w[k]))
                dfs = self.STEP * sum(cov[i + k] for k in range(L) if src[k] != w[k])
                gain = (sc - orig) + self._lc() * cpr + self.lambda_learned * (atk - dfs)
                if L == 1 and fbm != "off":
                    try:
                        from . import framebias
                    except ImportError:
                        framebias = None
                    if framebias is not None:
                        gain += framebias.score_diff(
                            w, src,
                            clause[i - 1] if i > 0 else None,
                            clause[i + 1] if i + 1 < len(clause) else None, fbm)
                if L == 1 and gvon:
                    gain += ghostveto.pen(
                        w, src,
                        clause[i - 1] if i > 0 else None,
                        clause[i + 1] if i + 1 < len(clause) else None)
                results.append((gain, clause[:i] + w + clause[i + L:], (i, src, w)))
        return results

    def _court_scores(self, clause, props):
        from . import escstop
        scores = {}
        try:
            from . import discjudge
            use_disc = settings.get("disc_judge", True) and discjudge.available()
        except Exception:
            use_disc = False
        if use_disc:
            escstop.check()
            sc = discjudge.score(clause, props)
            if sc is not None and len(sc) == len(props):
                for p, v in zip(props, sc):
                    scores[p] = v + self._judge_extra(p, clause)
                return scores
        for p in props:
            escstop.check()
            scores[p] = self._cond_pll(p) + self._judge_extra(p, clause)
        return scores

    def _cond_pll(self, s):
        bert = getattr(self, "judge", None) or self.bert
        ids = bert.encode(s)
        batch = []
        for k in range(len(s)):
            m = ids[:]
            m[k + 1] = bert.mask
            batch.append(m)
        tot = 0.0
        for st in range(0, len(batch), 64):
            logits = bert.run(batch[st:st + 64])
            for j in range(len(logits)):
                k = st + j
                tid = bert.token_id(s[k])
                if tid is None:
                    tot += self.OOV_FLOOR
                    continue
                tot += float(log_softmax(logits[j][k + 1])[tid])
        return tot

    def _judge_extra(self, s, inp, parts=None):
        diffs = [k for k in range(len(s)) if s[k] != inp[k]]
        if not diffs:
            if parts is not None:
                parts.update(corpus=0.0, learned=0.0, frame=0.0, ghost=0.0)
            return 0.0
        corpus = 0.0
        for k in diffs:
            corpus += self._lc() * (math.log(1 + wordphon.corpus_freq(s[k]))
                                    - math.log(1 + wordphon.corpus_freq(inp[k])))
        learned = 0.0
        dset = set(diffs)
        for text, sign, table in ((s, 1, wordphon.attack_levels()),
                                  (inp, -1, wordphon.defense_levels())):
            for w, lv in table.items():
                st = text.find(w)
                while st != -1:
                    if any(st <= d < st + len(w) for d in dset):
                        learned += sign * self.lambda_learned * self.STEP * self._steps(lv)
                        break
                    st = text.find(w, st + 1)
        frame = 0.0
        fbm = settings.get("frame_prior") or "off"
        if fbm != "off":
            try:
                from . import framebias
            except ImportError:
                framebias = None
            if framebias is not None:
                for k in diffs:
                    frame += framebias.score_diff(
                        s[k], inp[k],
                        s[k - 1] if k > 0 else None,
                        s[k + 1] if k + 1 < len(s) else None, fbm)
        ghost = 0.0
        if settings.get("ghost_veto"):
            for k in diffs:
                ghost += ghostveto.pen(
                    s[k], inp[k],
                    s[k - 1] if k > 0 else None,
                    s[k + 1] if k + 1 < len(s) else None)
        if parts is not None:
            parts.update(corpus=corpus, learned=learned, frame=frame, ghost=ghost)
        return corpus + learned + frame + ghost

    _SAMECHAR_STOP = set("的得地在再了是他她它牠祂你妳您各個")

    def _repeat_groups(self, clause):
        pos = {}
        for k, ch in enumerate(clause):
            if ch in self._SAMECHAR_STOP or not ("一" <= ch <= "鿿"):
                continue
            pos.setdefault(ch, []).append(k)
        return {c: ps for c, ps in pos.items() if len(ps) >= 2}

    def _samechar_variants(self, clause, props):
        groups = self._repeat_groups(clause)
        if not groups:
            return []
        out = []

        def add(m):
            if m != clause and m not in props and m not in out:
                out.append(m)

        for p in props:
            if p == clause or len(p) != len(clause):
                continue
            for ch, ps in groups.items():
                vals = {p[k] for k in ps}
                if len(vals) == 1:
                    continue
                for nv in vals:
                    if nv != ch:
                        m = list(p)
                        for k in ps:
                            m[k] = nv
                        add("".join(m))
        by = self._candidates_by_span(clause)
        for ch, ps in groups.items():
            cands = []
            for k in ps:
                for w in by.get((k, 1), ()):
                    if w != ch and w not in cands:
                        cands.append(w)
            for w in cands[:4]:
                m = list(clause)
                for k in ps:
                    m[k] = w
                add("".join(m))
        return out

    SAMECHAR_BONUS = 1.0

    @staticmethod
    def _samechar_mode():
        m = settings.get("same_char_first")
        if m is True:
            return "first"
        return m if m in ("bonus", "first") else "off"

    def _samechar_block(self, clause, props):
        groups = self._repeat_groups(clause)
        if not groups:
            return []
        block = []
        for p in props:
            if p == clause or len(p) != len(clause):
                continue
            touched, broken = False, False
            for ch, ps in groups.items():
                vals = {p[k] for k in ps}
                if len(vals) == 1:
                    if ch not in vals:
                        touched = True
                else:
                    broken = True
            if touched and not broken:
                block.append(p)
        return block

    _REDUP_SWAP = {"個個": "各個", "各個": "個個"}

    def _redup_props(self, clause):
        out = []
        for src, dst in self._REDUP_SWAP.items():
            k = clause.find(src)
            while k != -1:
                v = clause[:k] + dst + clause[k + len(src):]
                if v != clause and v not in out:
                    out.append(v)
                k = clause.find(src, k + 1)
        return out

    def _lattice_props(self, clause):
        try:
            from . import latticeprop
            by = self._candidates_by_span(clause)
            out = []
            for _sc, s in latticeprop.paths(clause, lambda i: by.get((i, 1), [])):
                s2 = self._pron_canon(s, clause)
                if s2 != clause and s2 not in out:
                    out.append(s2)
            return out
        except Exception:
            return []

    WORD_DIRECT_CAP = 6

    def _word_direct_props(self, clause, best):
        props = []
        swap_on = settings.get("word_swap_ticket", False)
        for (i, L), words in self._candidates_by_span(clause).items():
            if L < 2:
                continue
            src_in = wordphon.corpus_freq(clause[i:i + L]) > 0
            if src_in:
                if not swap_on:
                    continue
                words = [w for w in words if w in wordphon._word2seqs]
                if not words:
                    continue
            _n = len(words)
            _mode = settings.get("word_ticket_mode", "uniq")
            free = settings.get("uniq_word_ticket", True) and (
                _n == 1 or (_mode == "pair" and _n <= 2) or _mode == "all")
            for w in words[:settings.get("word_ticket_span", 2)]:
                wf = wordphon.corpus_freq(w)
                if wf < 800 and not free:
                    continue
                for host in (clause, best):
                    cand = host[:i] + w + host[i + L:]
                    if cand != host and all(cand != p for _f, p in props):
                        props.append((wf, cand))
        props.sort(key=lambda x: -x[0])
        return [p for _f, p in props[:self.WORD_DIRECT_CAP]]

    def _f7_props(self, clause, best):
        lv = wordphon._userforce_level
        if not lv:
            return []
        out = []
        for (i, L), words in self._candidates_by_span(clause).items():
            for w in words:
                if w not in lv:
                    continue
                for host in (clause, best):
                    cand = host[:i] + w + host[i + L:]
                    if cand != host and cand not in out:
                        out.append(cand)
        return out

    ESCORT_CAP = 16
    CHAR_TICKET_CAP = 40

    VIP_BAND = 8.0

    def _celebrity_props(self, clause):
        if not settings.get("cycle_vip", True):
            return []
        lcs = getattr(self, "last_court_sc", None)
        if not lcs or lcs[0] != clause:
            return []
        scores = lcs[1]
        cands = sorted((p for p in scores if p != clause),
                       key=lambda p: -scores[p])
        if not cands:
            return []
        floor = scores[cands[0]] - self.VIP_BAND
        return [p for p in cands[:3] if scores[p] >= floor]

    def _escort_props(self, clause):
        from . import escort
        hits = []
        n = len(clause)
        for w in escort.ticket_words():
            L = len(w)
            if L > n:
                continue
            for i in range(n - L + 1):
                span = clause[i:i + L]
                if span == w or not self._homophone_ok(span, w):
                    continue
                hits.append((i, L, w, escort.weight("word", w)))
            if len(hits) >= 12:
                break
        pmap = escort.ticket_pairs()
        for i, ch in enumerate(clause):
            for b in pmap.get(ch, ()):
                if b != ch and len(hits) < 20:
                    hits.append((i, 1, b, escort.weight("pair", (ch, b))))
        chits = []
        for g in escort.chars():
            for i, ch in enumerate(clause):
                if g != ch and phonetics.same_sound(ch, g):
                    chits.append((i, 1, g, escort.weight("char", g)))
        chits.sort(key=lambda h: -h[3])
        hits.extend(chits[:self.CHAR_TICKET_CAP])
        cands = {}
        for i, L, w, wt in hits:
            s = clause[:i] + w + clause[i + L:]
            cands[s] = max(cands.get(s, 0), wt)
        for a in range(len(hits)):
            i1, L1, w1, wt1 = hits[a]
            for b in range(a + 1, len(hits)):
                i2, L2, w2, wt2 = hits[b]
                if i1 + L1 <= i2 or i2 + L2 <= i1:
                    lo, hi = ((i1, L1, w1), (i2, L2, w2)) if i1 < i2 \
                        else ((i2, L2, w2), (i1, L1, w1))
                    s = (clause[:lo[0]] + lo[2] + clause[lo[0] + lo[1]:hi[0]]
                         + hi[2] + clause[hi[0] + hi[1]:])
                    cands[s] = max(cands.get(s, 0), wt1 + wt2)
        out = []
        for s, _wt in sorted(cands.items(), key=lambda x: -x[1]):
            s = self._pron_canon(s, clause)
            if s != clause and s not in out:
                out.append(s)
            if len(out) >= self.ESCORT_CAP:
                break
        return out

    HOLLOW_CAP = 6
    HOLLOW_TOPK = 8
    HOLLOW_TICKETS = 3
    HOLLOW_OUT = 3

    def _escort_positions(self, clause):
        try:
            from . import escort
            pos, n = set(), len(clause)
            for w in escort.ticket_words():
                L = len(w)
                if L > n:
                    continue
                for i in range(n - L + 1):
                    span = clause[i:i + L]
                    if span != w and self._homophone_ok(span, w):
                        pos.update(range(i, i + L))
            pmap = escort.ticket_pairs()
            for i, ch in enumerate(clause):
                if any(b != ch for b in pmap.get(ch, ())):
                    pos.add(i)
            for g in escort.ticket_chars():
                for i, ch in enumerate(clause):
                    if g != ch and phonetics.same_sound(ch, g):
                        pos.add(i)
            return pos
        except Exception:
            return set()

    def _detmask_props(self, clause):
        try:
            sus = {k for k, _p in self._det_pairs(clause)}
            pos = sorted(sus | self._escort_positions(clause))[:self.HOLLOW_CAP]
            if not pos:
                return []
            bert = getattr(self, "judge", None) or self.bert
            ids = bert.encode(clause)
            for k in pos:
                ids[k + 1] = bert.mask
            logits = bert.run([ids])[0]
            beam = [("", 0.0)]
            base = 0.0
            for k in pos:
                lg = logits[k + 1]
                slot = []
                for ch in phonetics.circle(clause[k]):
                    t = bert.token_id(ch)
                    if t is not None:
                        slot.append((float(lg[t]), ch))
                if not slot:
                    return []
                slot.sort(reverse=True)
                beam = [(s + ch, sc + w) for s, sc in beam
                        for w, ch in slot[:self.HOLLOW_TOPK]]
                beam.sort(key=lambda x: -x[1])
                beam = beam[:self.HOLLOW_TOPK]
            out = []
            for s, _sc in beam:
                cur = clause
                for j, k in enumerate(pos):
                    cur = cur[:k] + s[j] + cur[k + 1:]
                cur = self._pron_canon(cur, clause)
                if cur != clause and cur not in out:
                    out.append(cur)
            out = out[:self.HOLLOW_OUT]
            if settings.get("escort_words"):
                got = 0
                for m in self._escort_props(clause):
                    if got >= self.HOLLOW_TICKETS:
                        break
                    if len(m) != len(clause) or m in out:
                        continue
                    if {i for i, (a, b) in enumerate(zip(clause, m)) if a != b} & sus:
                        out.append(m)
                        got += 1
            return out
        except Exception:
            return []

    WIN_K = 5
    WIN_TH = 0.0
    WIN_OUT = 6

    def _window_props(self, clause):
        try:
            from . import detprop
            bert = getattr(self, "judge", None) or self.bert
            n = len(clause)
            han = lambda i: 0 <= i < n and "一" <= clause[i] <= "鿿"
            wins = []
            for p, _pr in detprop.suspects(clause, th=self.WIN_TH, cap=self.WIN_K):
                for w in ((p,), (p - 1, p), (p, p + 1)):
                    if all(han(i) for i in w) and w not in wins:
                        wins.append(w)
            if not wins:
                return []
            base = bert.encode(clause)
            batch = []
            for w in wins:
                ids = list(base)
                for i in w:
                    ids[i + 1] = bert.mask
                batch.append(ids)
            logits = bert.run(batch)
            cands = {}
            for wi, w in enumerate(wins):
                lps = {i: log_softmax(logits[wi][i + 1]) for i in w}
                orig = 0.0
                for i in w:
                    t = bert.token_id(clause[i])
                    orig += float(lps[i][t]) if t is not None else -30.0
                beam = [("", 0.0)]
                for i in w:
                    slot = sorted(((float(lps[i][t]), ch) for ch in phonetics.circle(clause[i])
                                   if (t := bert.token_id(ch)) is not None), reverse=True)[:4]
                    beam = sorted([(s + ch, sc + v) for s, sc in beam for v, ch in slot], key=lambda x: -x[1])[:4]
                old = clause[w[0]:w[-1] + 1]
                for s, sc in beam[:2 if len(w) == 1 else 3]:
                    if s != old:
                        cur = clause[:w[0]] + s + clause[w[-1] + 1:]
                        cands[cur] = max(cands.get(cur, -1e9), sc - orig)
            out = []
            for _sc, x in sorted(((sc, x) for x, sc in cands.items()), reverse=True):
                x = self._pron_canon(x, clause)
                if x != clause and x not in out:
                    out.append(x)
                if len(out) >= self.WIN_OUT:
                    break
            return out
        except Exception:
            return []

    def _pron_canon(self, p, clause):
        if len(p) != len(clause):
            return p
        out = list(p)
        for k, (a, b) in enumerate(zip(clause, p)):
            if a != b and a in self._PRON_GUARD and b in self._PRON_GUARD:
                out[k] = a
        return "".join(out)

    def _correct_clause(self, clause):
        proposals = [clause]
        cur = clause
        from . import escstop
        for _ in range(self.max_iter):
            escstop.check()
            scored = [x for x in self._score(cur, anchor=clause) if x[1] != cur]
            if not scored:
                break
            scored.sort(key=lambda x: -x[0])
            _gfloor = self._prop_gain()
            for g, cand, _e in scored[:self._prop_top()]:
                cand = self._pron_canon(cand, clause)
                if g > _gfloor and cand not in proposals:
                    proposals.append(cand)
            _ps = self._prop_perslot()
            if _ps:
                per = {}
                for g, cand, e in scored:
                    per.setdefault((e[0], e[1]), []).append((g, cand))
                for _k, lst in per.items():
                    lst.sort(key=lambda x: -x[0])
                    for g, cand in lst[:_ps]:
                        cand = self._pron_canon(cand, clause)
                        if cand not in proposals:
                            proposals.append(cand)
            gain, best = scored[0][0], scored[0][1]
            if gain <= self.margin:
                break
            cur = best
            canon = self._pron_canon(cur, clause)
            if canon not in proposals:
                proposals.append(canon)
        ni, ta = settings.get("pron_ni", ""), settings.get("pron_ta", "")
        scm = self._samechar_mode()
        wd = [m for m in (self._pron_canon(p, clause)
                          for p in self._word_direct_props(clause, cur))
              if m != clause]
        f7 = [m for m in (self._pron_canon(p, clause) for p in self._f7_props(clause, cur))
              if m != clause] if settings.get("f7_direct", True) else []
        rk = int(settings.get("respell_prop") or 0)
        if rk:
            from . import garble
            rsp = [m for m in (self._pron_canon(p, clause) for p in garble.respell(clause, k=rk)) if m != clause]
        else:
            rsp = []
        extra =self._samechar_variants(clause, proposals) if scm != "off" else []
        lat = self._lattice_props(clause) if settings.get("lattice_prop") else []
        det = self._detmask_props(clause) if settings.get("det_prop") else []
        win = self._window_props(clause) if settings.get("det_windows", True) else []
        rd = self._redup_props(clause)
        esc = self._escort_props(clause) if (settings.get("escort_words") and not (
            settings.get("det_prop") and settings.get("hollow_takeover", True))) else []
        if len(proposals) + len(wd) + len(extra) + len(lat) + len(det) + len(win) + len(rd) \
                + len(esc) + len(f7) + len(rsp) == 1:
            return pronoun.apply_pref(clause, ni, ta)
        _cap = self._prop_cap()
        props = proposals[:_cap] + [m for m in wd if m not in proposals[:_cap]]
        props += [m for m in f7 if m not in props]
        props += [m for m in rsp if m not in props]
        props += [m for m in rd if m not in props]
        props += [m for m in extra if m not in props]
        props += [m for m in lat if m not in props]
        props += [m for m in det if m not in props]
        props += [m for m in win if m not in props]
        props += [m for m in esc if m not in props]
        scores = self._court_scores(clause, props)
        self.last_court = (clause, list(scores))
        self.last_court_sc = (clause, dict(scores))
        if scm == "bonus":
            for p in self._samechar_block(clause, props):
                scores[p] += self.SAMECHAR_BONUS
        base = scores[clause]
        winner = max(scores, key=scores.get)
        jm = 0.0 if settings.get("f1_no_guard") else self.JMARGIN
        result = None
        if scm == "first":
            blk = self._samechar_block(clause, props)
            if blk:
                sc = max(blk, key=scores.get)
                if scores[sc] > base + jm:
                    result = sc
        if result is None:
            result = winner if scores[winner] > base + jm else clause
        return pronoun.apply_pref(result, ni, ta)
