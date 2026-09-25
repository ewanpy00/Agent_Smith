from agent_smith.agent.limits import MBPP_LIMITS, SWEBENCH_LIMITS
from agent_smith.config import load_sandbox_config
from models import SolutionOutput, StepMetrics


def test_sandbox_template_matches_model_defaults():
    from models import SandboxConfig

    assert load_sandbox_config("sandbox_template.json") == SandboxConfig()


def test_solution_output_roundtrip():
    step = StepMetrics(step=1, input_tokens=1, output_tokens=1, request_time_ms=1.0)
    out = SolutionOutput(
        task_id="1", benchmark="mbpp", success=True, solution="x", iterations=1,
        total_requests=1, total_input_tokens=1, total_output_tokens=1,
        total_time_seconds=0.1, steps=[step],
    )
    assert SolutionOutput.model_validate_json(out.model_dump_json()) == out


def test_limits_match_subject():
    assert (MBPP_LIMITS.max_iterations, MBPP_LIMITS.timeout_seconds) == (10, 120)
    assert (SWEBENCH_LIMITS.max_iterations, SWEBENCH_LIMITS.timeout_seconds) == (30, 900)
