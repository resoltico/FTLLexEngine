"""Aggregated integration e2e test surface."""

from tests.integration_e2e_cases.essential_parse_format_tests_run_in_every_ci_build import *  # noqa: F403 - re-export split test surface
from tests.integration_e2e_cases.essential_parse_format_tests_run_in_every_ci_build_2 import *  # noqa: F403 - re-export split test surface
from tests.integration_e2e_cases.intensive_round_trip_tests_fuzz_marked_run_with_pytest_m_fuzz import *  # noqa: F403 - re-export split test surface
from tests.integration_e2e_cases.locale_code_validation import *  # noqa: F403 - re-export split test surface
from tests.integration_e2e_cases.multi_module_pipeline_tests import *  # noqa: F403 - re-export split test surface
from tests.integration_e2e_cases.number_literal_invariant_and_roundtrip import *  # noqa: F403 - re-export split test surface
