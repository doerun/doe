"""Prepare the pinned SqueezeNet application with provider selection and observations."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def identity(path: Path) -> dict:
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--consumer-root', required=True, type=Path)
    parser.add_argument('--upstream', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    policy_path = repo / 'config/onnx-vulkan-campaign.json'
    policy = json.loads(policy_path.read_text())
    if args.out.exists():
        parser.error('Output must be new')
    args.out.mkdir(parents=True)
    source = args.upstream / policy['application']['path']
    model = args.upstream / 'squeezenet.onnx'
    if identity(source)['sha256'] != policy['application']['sha256'] or identity(model)['sha256'] != policy['application']['modelSha256']:
        raise ValueError('Upstream application/model identity drift')
    original = source.read_text()
    modified = original.replace('#include <vector>', '#include <vector>\n#include "application-provider.h"', 1)
    modified = modified.replace('Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "test");',
        'Ort::Env env(std::getenv("CAMPAIGN_VERBOSE") ? ORT_LOGGING_LEVEL_VERBOSE : ORT_LOGGING_LEVEL_WARNING, "test");', 1)
    start = modified.index('  Ort::ThrowOnError(api.CreateTensorRTProviderOptions')
    end = modified.index('  Ort::Session session(', start)
    modified = modified[:start] + '  CampaignProvider integration(env, session_options);\n\n' + modified[end:]
    modified = modified.replace('  const auto& api = Ort::GetApi();\n  OrtTensorRTProviderOptionsV2* tensorrt_options;\n', '', 1)
    call = 'session.Run(Ort::RunOptions{nullptr}, input_node_names.data(), &input_tensor, 1, output_node_names.data(), 1)'
    if modified.count(call) != 1:
        raise ValueError('Upstream Run boundary changed')
    modified = modified.replace(call, 'campaign_run(session, input_node_names.data(), &input_tensor, 1, output_node_names.data(), 1)', 1)
    modified = modified.replace('  run_ort_trt();\n  return 0;',
        '  try { run_ort_trt(); return 0; }\n'
        '  catch (const std::exception& error) { std::cerr << error.what() << "\\n"; return 1; }', 1)
    (args.out / 'main.cpp').write_text(modified)
    shutil.copyfile(model, args.out / 'squeezenet.onnx')
    headers = args.upstream / 'onnx-headers'
    header_source = json.loads((headers / 'source.json').read_text())
    if header_source['commit'] != '2d924974ef147392ced8409d36bd6d2e7fcc8a74':
        raise ValueError('Application C++ headers differ from ONNX 1.24.4')
    for item in header_source['files']:
        if identity(headers / item['path'])['sha256'] != item['sha256']:
            raise ValueError('Application header integrity failure')
    dawn_include = args.consumer_root / 'build/_deps/dawn-build/gen/include'
    libraries = list((args.consumer_root / 'venv').glob('lib/python*/site-packages/onnxruntime/capi/libonnxruntime.so.1.24.4'))
    if len(libraries) != 1:
        raise ValueError('Expected the pinned ONNX runtime core')
    shutil.copyfile(libraries[0], args.out / 'libonnxruntime.so.1')
    command = ['g++', '-std=c++17', '-O3', '-Wall', '-Wextra', '-Werror',
               '-I' + str(headers),
               '-I' + str(dawn_include), '-I' + str(Path(__file__).parent),
               str(args.out / 'main.cpp'), str(libraries[0]), '-ldl',
               '-Wl,-rpath,$ORIGIN', '-o', str(args.out / 'application')]
    subprocess.run(command, check=True)
    patch = subprocess.run(['diff', '-u', str(source), str(args.out / 'main.cpp')], capture_output=True, text=True)
    if patch.returncode != 1:
        raise ValueError('Provider substitution did not produce a bounded patch')
    (args.out / 'application.patch').write_text(patch.stdout)
    receipt = {'schemaVersion': 1, 'policy': identity(policy_path), 'upstreamSource': identity(source),
               'preparedSource': identity(args.out / 'main.cpp'), 'patch': identity(args.out / 'application.patch'),
               'providerIntegration': identity(Path(__file__).parent / 'application-provider.h'),
               'model': identity(model), 'onnxCore': identity(libraries[0]), 'applicationHeaders': header_source,
               'application': identity(args.out / 'application'),
               'command': command, 'builder': identity(Path(__file__))}
    (args.out / 'preparation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
