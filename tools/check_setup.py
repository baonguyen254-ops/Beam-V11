"""Read-only local installation check. Does not open or modify runtime data."""
import importlib.util
import json
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
assert sys.version_info >= (3,12), 'Python 3.12+ required'
for module in ('fastapi','uvicorn','websockets','bs4','tzdata'):
    assert importlib.util.find_spec(module), f'Missing dependency: {module}'
for name in ('floorplan.json','energy_baseline.json','or_capabilities.json','Hospital.osm','openstudio_results/eplustbl.htm'):
    assert (root/'beam-backend/data'/name).is_file(), 'Missing '+name
assert (root/'beam-backend/static/index.html').is_file(), 'Frontend needs rebuilding'
baseline=json.loads((root/'beam-backend/data/energy_baseline.json').read_text(encoding='utf-8'))
print('BEAM v11.1 dependencies, bundled UI and original source data: OK')
print('Baseline:',baseline.get('calibration_tier'),'| Hourly trace:',bool(baseline.get('hourly_electric_kw')))
print('Start the English demo with START_BEAM.bat or python RUN_BEAM.py --demo. Node.js is needed only for rebuilding.')
