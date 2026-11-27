import sys, json, scripts.ingest as i
ch,_,_ = i.collect_chunks()
out = {}
for c in ch: out.setdefault(c.source, []).append(c.section or '')
json.dump(out, open(sys.argv[1], 'w'))
