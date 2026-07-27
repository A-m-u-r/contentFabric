import saasshorts as s

words = [{"word": "w", "start": i * 0.45, "end": i * 0.45 + 0.36} for i in range(110)]
slices = [{"shot": {"visual_type": "talking", "speech": "x"}, "start": i * 7.5, "end": (i + 1) * 7.5}
          for i in range(6)]
old = s._split_long_slices([dict(x) for x in slices], words, max_len=5.0)
new = s._split_long_slices([dict(x) for x in slices], words)


def fmt(out):
    return " ".join("%.1f" % (x["end"] - x["start"]) for x in out)


print("45s / 6 shots, old flat 5s cap: %d clips: %s" % (len(old), fmt(old)))
print("45s / 6 shots, rhythm curve:    %d clips: %s" % (len(new), fmt(new)))
