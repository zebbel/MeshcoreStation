"""Limit this isolated dashboard release's CI checks; unrelated changes keep full checks."""
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
 'scripts/v4_test_scope.py','docs/web-version-switching.md',
 'meshcorestation/web/optimizer_api.py','meshcorestation/web/repeater_optimizer.html',
 'meshcorestation/web/assets/dashboard_footer.js','meshcorestation/web/assets/dashboard_footer.css',
 'meshcorestation/web/assets/updates.js','tests/test_dashboard_footer.cjs','tests/test_layout_panels.py','tests/test_updates_ui.cjs'
}


def neighbor_map_scope():
    if os.environ.get('GITHUB_REF')!='refs/heads/v4.0.0' or os.environ.get('GITHUB_EVENT_NAME')!='push' or __version__!='4.3.3':
        return False
    try:
        paths=set(subprocess.check_output(['git','diff','--name-only','HEAD^','HEAD'],text=True).splitlines())
    except subprocess.CalledProcessError:
        return False
    return bool(paths) and paths<=ALLOWED


def performance_calculation_scope():
    # Only this read-only calculation/chart correction can skip map/browser work.
    allowed={'.github/workflows/v4-release.yml','.github/workflows/production-regression.yml',
             'scripts/v4_test_scope.py','meshcorestation/__init__.py','meshcorestation/analyzer.py',
             'meshcorestation/storage/performance_view.py',
             'meshcorestation/web/assets/repeater_performance.js',
             'tests/test_performance_dashboard.py','tests/test_performance_ui.cjs',
             'README.md','docs/repeater-performance.md','docs/v4-release.md'}
    if os.environ.get('GITHUB_REF')!='refs/heads/v4.0.0' or os.environ.get('GITHUB_EVENT_NAME')!='push' or __version__!='4.3.4':
        return False
    try:
        paths=set(subprocess.check_output(['git','diff','--name-only','HEAD^','HEAD'],text=True).splitlines())
    except subprocess.CalledProcessError:
        return False
    return bool(paths) and paths<=allowed


def reply_retry_scope():
    allowed={'.github/workflows/v4-release.yml','.github/workflows/production-regression.yml',
             'scripts/v4_test_scope.py','meshcorestation/__init__.py','meshcorestation/analyzer.py',
             'meshcorestation/radio/reply_retries.py','meshcorestation/radio/companion.py',
             'meshcorestation/radio/channels_control.py','meshcorestation/runtime.py',
             'meshcorestation/storage/reply_store.py','meshcorestation/web/assets/reply_tracking.js',
             'tests/test_reply_retries.py','tests/test_reply_tracking_ui.cjs',
             'README.md','docs/bot-reply-retries.md','docs/user-guide.md','docs/v4-release.md'}
    if os.environ.get('GITHUB_REF')!='refs/heads/v4.0.0' or os.environ.get('GITHUB_EVENT_NAME')!='push' or __version__!='4.4.0':
        return False
    try:
        paths=set(subprocess.check_output(['git','diff','--name-only','HEAD^','HEAD'],text=True).splitlines())
    except subprocess.CalledProcessError:
        return False
    return bool(paths) and paths<=allowed


if __name__=='__main__':
    print('neighbor_map='+str(neighbor_map_scope()).lower())
    print('performance_calc='+str(performance_calculation_scope()).lower())
    print('reply_retry='+str(reply_retry_scope()).lower())
