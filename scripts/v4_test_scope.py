"""Limit this isolated map release's CI checks; unrelated changes keep full checks."""
import os
import subprocess
from meshcorestation import __version__

ALLOWED={
 '.github/workflows/v4-release.yml','.github/workflows/production-regression.yml',
 'README.md','docs/repeater-performance.md','docs/v4-release.md',
 'meshcorestation/__init__.py','meshcorestation/analyzer.py',
 'meshcorestation/web/performance_api.py','meshcorestation/web/layout.py',
 'meshcorestation/web/assets/ad_neighbor_communication_map.js',
 'meshcorestation/web/assets/repeater_performance.js','meshcorestation/web/assets/repeater_performance.css',
 'tests/test_performance_neighbor_map.py','tests/test_performance_neighbor_map_ui.cjs',
 'tests/test_performance_ui.cjs','tests/browser/serve.py',
 'tests/browser/performance_neighbor_map.cjs','tests/browser/repeater_performance.cjs',
 'scripts/v4_test_scope.py'
}


def neighbor_map_scope():
    if os.environ.get('GITHUB_REF')!='refs/heads/v4.0.0' or os.environ.get('GITHUB_EVENT_NAME')!='push' or __version__!='4.3.2':
        return False
    try:
        paths=set(subprocess.check_output(['git','diff','--name-only','HEAD^','HEAD'],text=True).splitlines())
    except subprocess.CalledProcessError:
        return False
    return bool(paths) and paths<=ALLOWED


if __name__=='__main__':
    print('neighbor_map='+str(neighbor_map_scope()).lower())
