import subprocess,sys,types,unittest,json,tempfile,hashlib
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT));REF='origin/b/feedback-method'
def source(path):return subprocess.check_output(['git','show',REF+':'+path]).decode('utf-8')
def load(name,path):
 m=types.ModuleType(name);m.__file__=str(ROOT/path);sys.modules[name]=m;exec(compile(source(path),m.__file__,'exec'),m.__dict__);return m
import src.feedback,src.runtime
selective=load('src.feedback.selective','src/feedback/selective.py');src.feedback.selective=selective
runner=load('src.runtime.runner','src/runtime/runner.py');src.runtime.runner=runner
suite=unittest.defaultTestLoader.discover('tests')
btests=load('b_selective_tests','tests/test_selective_feedback.py');suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(btests))
r=unittest.TextTestRunner(verbosity=1).run(suite)
from src.runtime.backend import FakeBackend
from src.runtime.config import load_course_config
from src.evaluation.turns_reader import read_turns
from src.evaluation.tool_audit import audit_tool_attempts
cfg=load_course_config();checks=[]
with tempfile.TemporaryDirectory(prefix='b-cpu-') as tmp:
 for threshold in (12,24,48):
  for c in ('C','D'):
   backend=FakeBackend(replies=["Action:\nprint(reverse_string('abcdefghijklmnopqrstuvwxyz'))\nEnd Action",'Answer: ok'])
   record=runner.run_episode(task_id='message_decoder/specific_decoded_character',condition=c,cfg=cfg,backend=backend,runs_root=tmp,method_config={'min_match_chars':threshold},run_id=f'cpu-{c}-{threshold}')
   ts=read_turns(record['turns_path']);report=audit_tool_attempts(ts,{'tool_attempts_per_action':4,'tool_attempts_per_task':32})
   assert not report['issues']; assert record['episode']['model_calls']==2
   checks.append({'condition':c,'threshold':threshold,'config_sha256':record['episode']['config_sha256'],'audit_issues':report['issues'],'max_feedback_chars':max(len(t.get('feedback') or '') for t in ts)})
receipt={'reviewed_branch':REF,'reviewed_commit':subprocess.check_output(['git','rev-parse',REF]).decode().strip(),'suite_tests':r.testsRun,'suite_failures':len(r.failures),'suite_errors':len(r.errors),'six_cpu_smokes':checks,'scope':'B modules loaded from git objects into C checkout; CPU only, no GPU or DEV inference'}
Path('results/b_handoff_20261127/verification.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt,indent=2));sys.exit(0 if r.wasSuccessful() else 1)
