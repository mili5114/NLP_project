import sys,types,subprocess,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import src.feedback
p='src/feedback/selective.py';m=types.ModuleType('src.feedback.selective');m.__file__=p
exec(compile(subprocess.check_output(['git','show','origin/b/feedback-method:'+p]).decode('utf-8'),p,'exec'),m.__dict__)
from src.runtime.config import load_course_config
from src.runtime.runner import feedback_settings
cfg=load_course_config(); rows=[]
for threshold in (12,24,48):
 n=trigger=changed=omitted=chars_c=chars_d=0
 for path in Path('runs/dev_full_v5/DEV').rglob('turns.jsonl'):
  for line in path.read_text(encoding='utf-8').splitlines():
   t=json.loads(line)
   if t.get('feedback') is None: continue
   kw={'python_output':t.get('python_output') or '', 'events':t['events'],'settings':{**feedback_settings(cfg),'min_match_chars':threshold}}
   c=m.build_feedback_for_condition(condition='C',**kw);d=m.build_feedback_for_condition(condition='D',**kw)
   assert len(c['text'])<=2000 and len(d['text'])<=2000
   n+=1;trigger+=c['metadata']['rule_trigger_count']>0;changed+=c['text']!=d['text'];omitted+=c['metadata']['rule_trigger_count'];chars_c+=len(c['text']);chars_d+=len(d['text'])
 rows.append({'min_match_chars':threshold,'replayed_feedbacks':n,'triggered_feedbacks':trigger,'changed_visible_feedbacks':changed,'omitted_events':omitted,'C_total_chars':chars_c,'D_total_chars':chars_d})
Path('results/b_handoff_20261127/replay.json').write_text(json.dumps({'scope':'Offline replay of A/B DEV v5 trajectories only; not C/D on-policy results and not candidate selection','rows':rows},indent=2)+'\n',encoding='utf-8');print(json.dumps(rows,indent=2))
