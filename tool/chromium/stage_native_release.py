"""Stage exact formal-build binaries for review, without building or publishing.

Artifact origin, source identity, Windows smoke and Android production signature
are checked here. Genuine extension/installer acceptance and corresponding-source
distribution are separate requirements before making a release public.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from tool.release_metadata import parse_pubspec, ReleaseMetadata
from tool.chromium.prepare_windows import PRODUCT, ROOT, resource_header, native_source_bytes
from tool.chromium.prepare_windows_runtime import sha256
from tool.chromium.sign_candidate import REPO_ID, PRODUCTION_CERT_SHA256, parse_verified_certificate_sha256
from tool.chromium.sign_native_android import command
from tool.chromium.titanium_product import PRODUCT_PACKAGE, verify_native_apk

ARTIFACTS = {'windows': 'native-windows-v022-development-not-release',
             'android': 'native-android-production-signed'}
WORKFLOW = '.github/workflows/native-android-production.yml'
SMOKE_CHECKS = {'native_browser_started', 'native_product_webui', 'native_upstream_notices',
                'native_legacy_bookmark_import', 'native_legacy_bookmark_dedup',
                'native_video_title_saved', 'native_player_resume_from_legacy',
                'native_player_position_saved', 'native_player_reopen_resume',
                'native_browser_video_download', 'native_completed_download_in_library',
                'native_downloaded_video_player', 'native_saved_external_subtitle_loaded',
                'original_library_unchanged', 'original_preferences_unchanged',
                'original_subtitle_unchanged'}
VIDEO_CAPTURE_CHECKS = {'capture_screen_and_quality_options', 'native_capture_download_exact_bytes',
    'generic_video_detected', 'youtube_muxed_quality_detected', 'instagram_video_detected',
    'other_profile_excluded', 'encrypted_hls_rejected_with_reason', 'hls_actual_quality_selected',
    'hls_resolved_to_mp4_parts', 'hls_pause', 'hls_resume', 'hls_survives_hub_navigation',
    'hls_exact_assembled_bytes', 'hls_partial_files_removed', 'hls_cancel', 'hls_cancel_not_in_library',
    'hls_automatically_in_library', 'hls_saved_video_playable', 'same_document_video_change_rejected',
    'stale_source_document_rejected', 'hls_pause_at_part_boundary',
    'youtube_adaptive_pair_detected', 'youtube_adaptive_pair_exact_bytes',
    'protected_dash_rejected', 'dash_external_entities_rejected', 'dash_missing_declared_audio_rejected',
    'dash_segment_list_and_timeline_resolved', 'dash_numbered_template_resolved',
    'dash_tracks_exact_original_bytes', 'dash_library_includes_companion_audio',
    'dash_video_and_audio_play_together', 'dash_seek_rate_and_volume_synchronized',
    'dash_pause_stops_audio', 'dash_pair_survives_browser_restart',
    'hls_transport_stream_resolved', 'transport_stream_saved_as_mp4',
    'transport_mp4_video_and_audio_decoded', 'direct_transport_stream_converted',
    'invalid_transport_stream_not_registered', 'transport_processing_origin_isolated',
    'transmux_processor_released', 'active_transmux_browser_shutdown',
    'active_transmux_partial_cleanup'}
VIDEO_CAPTURE_CHECKS |= {
    'html_response_rejected_bad-video.mp4', 'html_response_rejected_fake-video.mp4',
    'direct_webm_saved_video_playable', 'direct_webm_delete_removes_file_and_marker',
    'tab_picker_excludes_other_profile', 'native_scan_only_selected_tab', 'forged_tab_token_rejected',
    'navigated_tab_token_rejected', 'saved_pair_reports_combined_size', 'non_library_file_delete_rejected',
    'record_only_delete_preserves_media_bytes', 'pair_delete_removes_video_audio_and_completion_marker',
    'pair_delete_preserves_other_saved_video', 'deleted_pair_disappears_from_library',
    'source_no_referrer_policy_preserved',
    'progress_history_clear_preserves_saved_media', 'progress_history_dismissal_survives_hub_reload',
    'generic_hls_pair_quality_and_audio', 'generic_hls_pair_audio_exact_bytes', 'generic_hls_pair_video_exact_bytes',
    'generic_hls_mixed_pair_quality_and_audio', 'generic_hls_mixed_pair_audio_exact_bytes',
    'generic_hls_mixed_pair_video_converted'}
UPDATE_UI_CHECKS = {
    'video_downloadhelper_below_adblock',
    'displayed_product_version_matches_manifest',
    'settings_tabs_switch_panels', 'selected_tab_only_requested',
    'download_progress_shows_percent_and_byte_counts',
    'android_verified_download_opens_security_screen',
    'android_return_offers_install_retry_and_export_location',
    'install_hidden_before_verification', 'install_shown_after_verification',
    'hash_error_does_not_offer_install', 'cancel_never_requests_install', 'confirm_requests_install_once'}


def require(condition: bool, message: str) -> None:
    if not condition: raise ValueError(message)


def digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def select_artifacts(run: dict, listing: dict, commit: str, run_id: int) -> dict:
    require(type(run_id) is int and run_id > 0, 'Invalid formal build run ID')
    require(re.fullmatch('[a-f0-9]{40}', commit) is not None, 'Invalid integration commit')
    require(all(run.get(key) == value for key, value in {
        'id': run_id, 'head_sha': commit, 'head_branch': 'main', 'event': 'workflow_dispatch',
        'status': 'completed', 'conclusion': 'success', 'path': WORKFLOW}.items()),
        'Formal build must have completed successfully on this exact main commit')
    require(run.get('repository', {}).get('id') == REPO_ID and
            run.get('head_repository', {}).get('id') == REPO_ID, 'Foreign formal build repository')
    rows = listing.get('artifacts', [])
    require(listing.get('total_count') == len(rows), 'Artifact metadata must include every page')
    selected = {}
    for platform, name in ARTIFACTS.items():
        matches = [row for row in rows if row.get('name') == name]
        require(len(matches) == 1, 'Missing or ambiguous formal artifact: ' + name)
        artifact = matches[0]
        origin = artifact.get('workflow_run', {})
        require(type(artifact.get('id')) is int and artifact['id'] > 0 and
                artifact.get('expired') is False and artifact.get('size_in_bytes', 0) > 0 and
                isinstance(artifact.get('digest'), str) and
                artifact['digest'].startswith('sha256:') and digest(artifact['digest'][7:]),
                'Invalid, expired or unhashed artifact: ' + name)
        require(origin.get('id') == run_id and origin.get('head_sha') == commit and
                origin.get('head_branch') == 'main' and origin.get('repository_id') == REPO_ID and
                origin.get('head_repository_id') == REPO_ID, 'Artifact belongs to a different build')
        selected[platform] = artifact
    require(selected['windows']['id'] != selected['android']['id'], 'Artifact IDs collide')
    return {'run_id': run_id, 'integration_commit': commit, 'artifacts': selected}


def windows_product_hashes() -> dict[str, str]:
    expected = {'resources.h': hashlib.sha256(resource_header()).hexdigest()}
    for directory in ('common', 'windows'):
        for path in (ROOT / f'native/chromium/{directory}/overlay').iterdir():
            if path.is_file(): expected[path.name] = hashlib.sha256(native_source_bytes(path)).hexdigest()
    return expected


def validate_windows(source: Path, commit: str, tree: str) -> dict:
    report = json.loads((source / 'native-provenance.json').read_text(encoding='utf-8'))
    require(report.get('native_source_compiled') is True and report.get('product') == PRODUCT and
            report.get('source_revision') == PRODUCT['chromium_revision'] and
            report.get('integration_commit') == commit and report.get('integration_tree') == tree,
            'Windows build source identity differs')
    overlay = report.get('overlay', {})
    require(overlay.get('product') == PRODUCT, 'Windows Chromium overlay product differs')
    for name, expected in windows_product_hashes().items():
        require(overlay.get('files', {}).get('chrome/browser/internet_browser/' + name) == expected,
                'Windows compiled product file differs: ' + name)
    files = report.get('files', {})
    for name in ('mini_installer.exe', 'chrome.7z'):
        require(sha256(source / name) == files.get(name), 'Windows artifact bytes differ: ' + name)
    runtime = json.loads((source / 'runtime-provenance.json').read_text(encoding='utf-8'))
    payload = runtime.get('files', {})
    require(runtime.get('kind') == 'NATIVE_RUNTIME_FROM_EXACT_INSTALLER_ARCHIVE' and
            runtime.get('layout') == 'standalone_flat' and
            runtime.get('appcontainer_read_execute_configured') is True and
            runtime.get('sandbox_disabled') is False and
            digest(runtime.get('appcontainer_acl_helper_sha256')) and
            runtime.get('product') == PRODUCT and runtime.get('integration_commit') == commit and
            runtime.get('source_archive_sha256') == files.get('chrome.7z') and
            digest(files.get('chrome.exe')) and payload.get('chrome.exe') == files['chrome.exe'],
            'Windows tested runtime does not match the installer archive')
    require(payload and all(digest(value) for value in payload.values()) and
            hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            == runtime.get('payload_fingerprint_sha256'), 'Invalid runtime payload fingerprint')
    smoke = json.loads((source / 'windows-smoke.json').read_text(encoding='utf-8'))
    checks = smoke.get('checks', {})
    require(smoke.get('kind') == 'NATIVE_WINDOWS_CONTROLLED_FIXTURE_SMOKE' and
            smoke.get('chrome_exe_sha256') == files['chrome.exe'] and 'error' not in smoke and
            SMOKE_CHECKS <= checks.keys() and all(value is True for value in checks.values()),
            'Packaged Windows native fixture/media smoke is missing or failed')
    capture = json.loads((source / 'video-capture-smoke.json').read_text(encoding='utf-8'))
    capture_checks = capture.get('checks', {})
    require(capture.get('kind') == 'NATIVE_CONTROLLED_VIDEO_CAPTURE_SMOKE' and
            capture.get('chrome_exe_sha256') == payload.get('chrome.exe') and
            digest(payload.get('chrome.dll')) and capture.get('chrome_dll_sha256') == payload['chrome.dll'] and
            capture.get('all_checks_passed') is True and 'error' not in capture and
            VIDEO_CAPTURE_CHECKS <= capture_checks.keys() and all(value is True for value in capture_checks.values()),
            'Packaged Windows video capture/stream smoke is missing, failed or from a different browser payload')
    renderer = json.loads((source / 'update-ui-smoke.json').read_text(encoding='utf-8'))
    renderer_checks = renderer.get('checks', {})
    require(renderer.get('kind') == 'UPDATE_RENDERER_FLOW_WITH_STUB_NATIVE_SERVICE' and
            renderer.get('chrome_exe_sha256') == files['chrome.exe'] and
            renderer.get('chrome_dll_sha256') == payload['chrome.dll'] and
            renderer.get('renderer_sources') == {name: sha256(ROOT / 'native/chromium/windows/resources' / name)
                                                 for name in ('index.html', 'app.js', 'style.css')} and
            UPDATE_UI_CHECKS <= renderer_checks.keys() and all(value is True for value in renderer_checks.values()),
            'Settings/update renderer flow is missing, failed or from a different browser')
    return report


def validate_android(source: Path, metadata: ReleaseMetadata, commit: str, tree: str,
                     run_id: int, aapt2: Path, apksigner: Path) -> dict:
    report = json.loads((source / 'android-release-provenance.json').read_text(encoding='utf-8'))
    expected = {'kind': 'PRODUCTION_SIGNED_NATIVE_ANDROID_BUILD', 'version': metadata.version,
        'version_code': metadata.version_code, 'package': PRODUCT_PACKAGE,
        'integration_commit': commit, 'integration_tree': tree, 'compiled': True,
        'production_signed': True, 'release_certificate_sha256': PRODUCTION_CERT_SHA256,
        'github_run_id': str(run_id)}
    require(all(report.get(key) == value for key, value in expected.items()) and
            report.get('compiled') is True and report.get('production_signed') is True and
            digest(report.get('source_apk_sha256')), 'Android production build identity differs')
    apk = source / f'Internet-browser-Android-v{metadata.version}.apk'
    require(sha256(apk) == report.get('signed_apk_sha256'), 'Signed APK bytes differ')
    verify_native_apk(apk, aapt2, PRODUCT_PACKAGE,
                      version_code=metadata.version_code, version_name=metadata.version)
    certificate = parse_verified_certificate_sha256(command(apksigner, 'verify', '--verbose', '--print-certs', str(apk)))
    require(certificate == PRODUCTION_CERT_SHA256, 'APK signature does not match the existing application')
    return report


def stage(windows: Path, android: Path, output: Path, selection: dict,
          metadata: ReleaseMetadata, commit: str, tree: str, aapt2: Path, apksigner: Path) -> dict:
    require(metadata.version == PRODUCT['app_version'] and selection.get('integration_commit') == commit,
            'Native and release source versions/commits must match')
    require(not output.exists() and not output.is_symlink(), 'Refusing to overwrite staged release files')
    validate_windows(windows, commit, tree)
    validate_android(android, metadata, commit, tree, selection['run_id'], aapt2, apksigner)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='native-release-stage-', dir=output.parent) as temporary:
        temporary = Path(temporary)
        names = {
            f'Internet-browser-Android-v{metadata.version}.apk': android / f'Internet-browser-Android-v{metadata.version}.apk',
            f'Internet-browser-Windows-Setup-v{metadata.version}.exe': windows / 'mini_installer.exe',
            'android-release-provenance.json': android / 'android-release-provenance.json',
            'windows-release-provenance.json': windows / 'native-provenance.json',
            'windows-runtime-provenance.json': windows / 'runtime-provenance.json',
            'windows-smoke.json': windows / 'windows-smoke.json',
            'video-capture-smoke.json': windows / 'video-capture-smoke.json',
            'update-ui-smoke.json': windows / 'update-ui-smoke.json'}
        copied = {}
        for name, source in names.items():
            target = temporary / name
            shutil.copyfile(source, target)
            copied[name] = sha256(target)
            require(copied[name] == sha256(source), 'Staged copy differs: ' + name)
        source_document = temporary / 'SOURCE-RECONSTRUCTION.md'
        shutil.copyfile(ROOT / 'docs/NATIVE_SOURCE_RECONSTRUCTION.md', source_document)
        copied[source_document.name] = sha256(source_document)
        notices_directory = ROOT / 'third_party/native-notices'
        notices = json.loads((notices_directory / 'manifest.json').read_text(encoding='utf-8'))
        for notice in notices:
            source = notices_directory / notice['file']
            require(source.resolve().parent == notices_directory.resolve() and
                    sha256(source) == notice['sha256'], 'Upstream notice bytes differ')
            target = temporary / ('upstream-' + notice['file'])
            shutil.copyfile(source, target)
            copied[target.name] = sha256(target)
        shutil.copyfile(notices_directory / 'manifest.json', temporary / 'upstream-notices-manifest.json')
        copied['upstream-notices-manifest.json'] = sha256(temporary / 'upstream-notices-manifest.json')
        source_inputs = {'kind': 'NATIVE_SOURCE_RECONSTRUCTION_INFORMATION',
                         'integration_commit': commit, 'integration_tree': tree,
                         'integration_source_archive_url':
                             f'https://github.com/sopo9880/Internet-browser/archive/{commit}.tar.gz',
                         'product': PRODUCT, 'upstream_notices': notices,
                         'complete_corresponding_source_included': False}
        (temporary / 'native-source-inputs.json').write_text(json.dumps(source_inputs, indent=2) + '\n', encoding='utf-8')
        copied['native-source-inputs.json'] = sha256(temporary / 'native-source-inputs.json')
        manifest = {'kind': 'EXACT_NATIVE_ARTIFACTS_STAGED_NOT_PUBLISHED', 'version': metadata.version,
                    'integration_tree': tree, **selection, 'files': copied,
                    'release_approved': False, 'published': False,
                    'remaining_acceptance': ['real Windows AdBlock and installer',
                                             'corresponding-source distribution',
                                             'remaining native feature acceptance'],
                    'android_device_validation': 'deferred until after release as agreed'}
        (temporary / 'native-release-staging.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        checksums = {**copied, 'native-release-staging.json': sha256(temporary / 'native-release-staging.json')}
        (temporary / 'SHA256SUMS.txt').write_text(''.join(f'{value}  {name}\n' for name, value in sorted(checksums.items())), encoding='utf-8')
        require(not output.exists(), 'Staged output appeared during verification')
        os.replace(temporary, output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('select', 'stage'))
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--windows', type=Path)
    parser.add_argument('--android', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--aapt2', type=Path)
    parser.add_argument('--apksigner', type=Path)
    args = parser.parse_args()
    require(args.run_id > 0 and os.environ.get('GITHUB_REF') == 'refs/heads/main', 'Staging requires main and a valid build run')
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    tree = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    metadata = parse_pubspec((ROOT / 'pubspec.yaml').read_text(encoding='utf-8'))
    require(metadata.version == PRODUCT['app_version'], 'Release/native product versions differ')
    selection = select_artifacts(json.loads(args.run.read_text()), json.loads(args.artifacts.read_text()), commit, args.run_id)
    if args.command == 'select':
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as outputs:
            for platform, artifact in selection['artifacts'].items(): outputs.write(f'{platform}_id={artifact["id"]}\n')
        print('Selected exact formal artifact IDs for', metadata.tag)
    else:
        if any(value is None for value in (args.windows, args.android, args.output, args.aapt2, args.apksigner)):
            parser.error('stage requires --windows, --android, --output, --aapt2 and --apksigner')
        stage(args.windows, args.android, args.output, selection, metadata, commit, tree, args.aapt2, args.apksigner)
        print('Exact APK/EXE staged with checksums; no compilation, signing or publication performed.')


if __name__ == '__main__': main()
