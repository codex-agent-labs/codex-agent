require 'minitest/autorun'
require 'open3'
require 'yaml'

class AndroidCore14CallerActionTest < Minitest::Test
  ACTION = YAML.load_file(File.join(__dir__, 'action.yml'))

  def test_fresh_originals_are_derived_from_pinned_inputs_not_the_download
    steps = ACTION.fetch('runs').fetch('steps')
    assert_equal %w[core13 prepare], steps.map { |step| step['id'] }.compact
    capture, download, prepare = steps
    assert_equal 'core-metadata', capture.fetch('with').fetch('sdk-family')
    assert_equal '13', capture.fetch('with').fetch('sdk-state-wave')
    assert_equal '${{ inputs.metadata-artifact-id }}', download.fetch('with').fetch('artifact-ids')
    assert_equal 'build/sdk-core-metadata-worker', download.fetch('with').fetch('path')
    script = prepare.fetch('run')
    assert_match(/require_no_signing_secret\(os\.environ\)/, script)
    assert_match(/from ci\.sdk_android_core14_fresh_inputs import prepare/, script)
    assert_match(/expected_metadata_receipt_sha256=os\.environ\['METADATA_RECEIPT_SHA256'\]/, script)
    assert_match(/native_compiler_archives=archives/, script)
    refute_match(/preparation.artifact|sign|attest|releaseTrust/i, ACTION.fetch('description'))
    assert_equal %w[metadata-receipt original-context replay-policy], ACTION.fetch('outputs').keys.sort
    python = script.split("<<'PY'\n", 2).last.split("\nPY", 2).first
    _, error, status = Open3.capture3('python3', '-c', 'import ast,sys; ast.parse(sys.stdin.read())', stdin_data: python)
    assert status.success?, error
  end
end
