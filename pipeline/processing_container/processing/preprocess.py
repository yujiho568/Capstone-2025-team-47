import numpy as np
def breakpoints_by_gap(times, gap_minutes=30):
    idx = []
    for i in range(1, len(times)):
        delta = (times[i] - times[i-1]).astype('timedelta64[m]').astype(int)
        if delta >= gap_minutes:
            idx.append(i)
    return idx
def sliding_windows(tokens, win=20, stride=1, max_windows=None):
    seqs = []
    N = len(tokens)
    for i in range(0, N - win + 1, stride):
        seqs.append(tokens[i:i+win])
        if max_windows and len(seqs) >= max_windows:
            break
    return seqs
def sequences_by_segments(tokens, break_idx, win=20, stride=5, max_per_seg=5):
    seqs = []
    starts = [0] + break_idx
    ends   = break_idx + [len(tokens)]
    for s, e in zip(starts, ends):
        seg = tokens[s:e]
        if len(seg) >= win:
            c = 0
            for i in range(0, len(seg) - win + 1, stride):
                seqs.append(seg[i:i+win])
                c += 1
                if max_per_seg and c >= max_per_seg:
                    break
    return seqs
