# Tools Ingested (Promoted and Skipped)

## Repo: langchain-ai/langchain

Total extracted: 508  
Total deduped: 166  
Total promoted: 124  
Total skipped: 42

### Promoted tools

| Name | Capability Category | Execution Kind | Confidence | Promotion Reason | Source Path |
| --- | --- | --- | --- | --- | --- |
| a_test_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/utils/test_json_schema.py |
| add | code_execution | python_function | 0.860 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| admin_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| afoo | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| another_dynamic_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_dynamic_tools.py |
| another_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_overrides.py |
| asimple_foo | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| async_multi_injection_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| async_runtime_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| async_search_tool | search_retrieval | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| async_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_state_schema.py |
| bar | code_execution | python_function | 0.820 | args_schema_strong_promoted | libs/langchain/tests/unit_tests/agents/test_structured_chat.py |
| base_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| calculate | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_selection.py |
| calculator | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| calculator | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_emulator.py |
| capture_state_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_state_schema.py |
| check_runtime_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| complex_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| concat | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/runnables/test_runnable_events_v1.py |
| config_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| counter_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_state_schema.py |
| custom_error_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_retry.py |
| custom_greeting | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/integration_tests/agents/middleware/test_shell_tool_integration.py |
| custom_state_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| dummy_function | code_execution | python_function | 0.820 | args_schema_strong_promoted | libs/core/tests/unit_tests/utils/test_function_calling.py |
| dynamic_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_dynamic_tools.py |
| error_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| extra_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_wrap_tool_call.py |
| extract_data | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| failing_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/runnables/test_runnable_events_v2.py |
| failing_tool_no_id | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/runnables/test_runnable_events_v2.py |
| FailingTool | code_execution | python_function | 0.820 | args_schema_strong_promoted | libs/langchain/tests/unit_tests/agents/test_agent_iterator.py |
| file_tool | file_filesystem | python_function | 0.900 | args_schema_strong_promoted | libs/partners/anthropic/langchain_anthropic/middleware/anthropic_tools.py |
| filter_tool | search_retrieval | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| find_pet | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain/tests/unit_tests/agents/test_agent.py |
| foo | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| foo2 | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| foo_args_jsons_schema | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| foo_args_jsons_schema_with_description | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| foo_args_schema | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| foo_args_schema_description | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| foo_description | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| func5 | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/utils/test_function_calling.py |
| get_current_weather | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/partners/ollama/tests/integration_tests/chat_models/test_chat_models.py |
| get_docs | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/runnables/test_runnable_events_v1.py |
| get_recipe | http_api_access | python_function | 0.900 | args_schema_strong_promoted | libs/partners/openai/tests/integration_tests/chat_models/test_responses_api.py |
| get_stock_price | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_selection.py |
| get_time | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/messages/test_utils.py |
| get_weather | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/partners/anthropic/tests/integration_tests/test_chat_models.py |
| get_weather | http_api_access | python_function | 0.900 | args_schema_strong_promoted | libs/partners/openai/tests/integration_tests/chat_models/test_responses_api.py |
| get_weather | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_selection.py |
| glob_search | search_retrieval | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/langchain/agents/middleware/file_search.py |
| grep_search | search_retrieval | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/langchain/agents/middleware/file_search.py |
| injected_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| injected_tool_with_schema | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| Intermediate Answer | search_retrieval | python_function | 0.820 | args_schema_strong_promoted | libs/langchain/langchain_classic/agents/self_ask_with_search/base.py |
| known_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| Lookup | code_execution | python_function | 0.820 | args_schema_strong_promoted | libs/langchain/tests/unit_tests/agents/test_agent_iterator.py |
| Lookup | file_filesystem | python_function | 0.820 | args_schema_strong_promoted | libs/langchain/langchain_classic/agents/react/base.py |
| magic_function | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/standard-tests/langchain_tests/integration_tests/chat_models.py |
| middleware_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| multi_injection_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| my_delta_tool | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| my_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/partners/anthropic/tests/integration_tests/test_chat_models.py |
| my_tool | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| my_tool | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_selection.py |
| my_tool_1 | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| my_tool_2 | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| my_tool_3 | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| my_tool_4 | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| my_tool_5 | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| my_tool_base | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| my_typechecked_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| narrow_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| no_op | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_state_schema.py |
| no_output_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_retry.py |
| nolimit_injected_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| nolimit_with_callbacks | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/runnables/test_runnable_events_v1.py |
| other_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| parameter_tool | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/utils/test_function_calling.py |
| pause_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_state_schema.py |
| Ping | code_execution | python_function | 0.820 | args_schema_strong_promoted | libs/langchain/tests/unit_tests/agents/test_agent_iterator.py |
| ping_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_state_schema.py |
| Plan | file_filesystem | python_function | 0.820 | args_schema_strong_promoted | libs/langchain/langchain_classic/agents/react/base.py |
| quoting_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| random_sleep_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_state_schema.py |
| random_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_state_schema.py |
| retry_always_failing_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_retry.py |
| retry_error_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_retry.py |
| retry_single_tool_timeout | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_retry.py |
| runtime_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| sample_tool | file_filesystem | python_function | 0.900 | args_schema_strong_promoted | libs/partners/anthropic/tests/integration_tests/test_chat_models.py |
| sample_tool_with_buffer | file_filesystem | python_function | 0.900 | args_schema_strong_promoted | libs/partners/anthropic/tests/integration_tests/test_chat_models.py |
| search_directory | search_retrieval | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/langchain/agents/middleware/file_search.py |
| search_directory_filtered | search_retrieval | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/langchain/agents/middleware/file_search.py |
| search_directory_recursive | search_retrieval | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/langchain/agents/middleware/file_search.py |
| search_tool | search_retrieval | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| select_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_selection.py |
| shell | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/langchain/agents/middleware/shell_tool.py |
| shell_exit_0 | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/integration_tests/agents/middleware/test_shell_tool_integration.py |
| shell_exit_1 | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/integration_tests/agents/middleware/test_shell_tool_integration.py |
| simple_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/integration_tests/agents/middleware/test_shell_tool_integration.py |
| some_module_with_functions | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| some_other_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| some_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| some_tool | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| stateful_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_state_schema.py |
| streamable_tool | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| sum | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_selection.py |
| sync_multi_injection_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| synchronous_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| text_tool | structured_data | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| thread_tools | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| threaded_tools | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| timedout_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_retry.py |
| timeout_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_state_schema.py |
| tool_a | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| tool_b | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| tool_c | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| tool_with_run_manager | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| tool_with_runtime | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| type_letter | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/partners/anthropic/tests/integration_tests/test_chat_models.py |
| typed_runtime_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_injected_runtime_create_agent.py |
| unicode_customer | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/standard-tests/langchain_tests/integration_tests/chat_models.py |
| unknown_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/core/test_tools.py |
| unstructured_tool_input | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/test_tools.py |
| value_error_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_retry.py |
| with_callbacks | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/runnables/test_runnable_events_v1.py |
| with_parameters | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests/unit_tests/runnables/test_runnable_events_v1.py |
| with_parameters_and_callbacks | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/core/tests_unit_tests/runnables/test_runnable_events_v1.py |
| working_tool | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/middleware/implementations/test_tool_retry.py |
| _wrapped | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/tests/unit_tests/agents/test_responses_spec.py |
| write_todos | code_execution | python_function | 0.900 | args_schema_strong_promoted | libs/langchain_v1/langchain/agents/middleware/todo.py |

### Skipped tools

| Name | Capability Category | Execution Kind | Confidence | Promotion Reason | Source Path |
| --- | --- | --- | --- | --- | --- |
| check_time | code_execution | python_function | 0.900 | args_schema_weak_not_promoted | libs/langchain/tests/unit_tests/agents/test_agent.py |
| delete_recycle | structured_data | http_request | 0.750 | low_confidence_not_promoted | libs/langchain/tests/mock_servers/robot/server.py |
| empty_tool | code_execution | python_function | 0.900 | args_schema_weak_not_promoted | libs/core/tests/unit_tests/utils/test_function_calling.py |
| empty_tool_input | code_execution | python_function | 0.900 | args_schema_weak_not_promoted | libs/core/tests_unit_tests/test_tools.py |
| get_ask_for_passphrase | http_api_access | http_request | 0.750 | low_confidence_not_promoted | libs/langchain/tests/mock_servers/robot/server.py |
| get_get_state | http_api_access | http_request | 0.750 | low_confidence_not_promoted | libs/langchain/tests/mock_servers/robot/server.py |
| get_location | structured_data | python_function | 0.900 | args_schema_weak_not_promoted | libs/langchain_v1/tests/unit_tests/agents/test_response_format.py |
| lint_imports.sh | code_execution | cli_command | 0.650 | low_confidence_not_promoted | libs/text-splitters/scripts/lint_imports.sh |
| magic_function_no_args | code_execution | python_function | 0.900 | args_schema_weak_not_promoted | libs/standard-tests/langchain_tests/integration_tests/chat_models.py |
| make_all | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/text-splitters/Makefile |
| make_benchmark | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/core/Makefile |
| make_check_imports | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/text-splitters/Makefile |
| make_check-lock | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/Makefile |
| make_check_version | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/core/Makefile |
| make_coverage | search_retrieval | cli_command | 0.700 | low_confidence_not_promoted | libs/langchain/Makefile |
| make_coverage_agents | search_retrieval | cli_command | 0.700 | low_confidence_not_promoted | libs/langchain_v1/Makefile |
| make_extended_tests | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/text-splitters/Makefile |
| make_help | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/text-splitters/Makefile |
| make_integration_test | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/partners/ollama/Makefile |
| make_integration_tests | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/langchain/Makefile |
| make_lint_package | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/text-splitters/Makefile |
| make_lint_tests | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/text-splitters/Makefile |
| make_lock | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/Makefile |
| make_refresh-profiles | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/model-profiles/Makefile |
| make_start_services | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/langchain_v1/Makefile |
| make_stop_services | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/langchain_v1/Makefile |
| make_test | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/langchain_v1/Makefile |
| make_test_fast | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/langchain_v1/Makefile |
| make_test_profile | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/text-splitters/Makefile |
| make_test_watch | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/text-splitters/Makefile |
| make_test_watch_extended | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/langchain/Makefile |
| make_tests | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/partners/exa/Makefile |
| make_type | file_filesystem | cli_command | 0.700 | low_confidence_not_promoted | libs/text-splitters/Makefile |
| _mock_structured_tool_with_artifact | code_execution | python_function | 0.900 | args_schema_weak_not_promoted | libs/core/tests/unit_tests/test_tools.py |
| parameterless | code_execution | python_function | 0.900 | args_schema_weak_not_promoted | libs/core/tests/unit_tests/runnables/test_runnable_events_v1.py |
| post_ask_for_help | http_api_access | http_request | 0.750 | low_confidence_not_promoted | libs/langchain/tests/mock_servers/robot/server.py |
| post_goto_x_y_z | http_api_access | http_request | 0.750 | low_confidence_not_promoted | libs/langchain/tests/mock_servers/robot/server.py |
| post_walk | http_api_access | http_request | 0.750 | low_confidence_not_promoted | libs/langchain/tests/mock_servers/robot/server.py |
| shell_tool | code_execution | python_function | 0.900 | args_schema_weak_not_promoted | libs/langchain_v1/langchain/agents/middleware/shell_tool.py |
| structured_tool_input | code_execution | python_function | 0.900 | args_schema_weak_not_promoted | libs/core/tests/unit_tests/test_tools.py |
| tool_func | code_execution | python_function | 0.900 | args_schema_weak_not_promoted | libs/core/tests_unit_tests/test_tools.py |
| tool_func_v1 | code_execution | python_function | 0.900 | args_schema_weak_not_promoted | libs/core/tests_unit_tests/test_tools.py |

## Repo: github/github-mcp-server

Total extracted: 11  
Total deduped: 11  
Total promoted: 0  
Total skipped: 11

### Promoted tools

_None promoted._

### Skipped tools

| Name | Capability Category | Execution Kind | Confidence | Promotion Reason | Source Path |
| --- | --- | --- | --- | --- | --- |
| build-ui | code_execution | cli_command | 0.650 | low_confidence_not_promoted | script/build-ui |
| conformance-test | structured_data | cli_command | 0.650 | low_confidence_not_promoted | script/conformance-test |
| fetch-icons | http_api_access | cli_command | 0.650 | low_confidence_not_promoted | script/fetch-icons |
| generate-docs | code_execution | cli_command | 0.650 | low_confidence_not_promoted | script/generate-docs |
| get-discussions | code_execution | cli_command | 0.650 | low_confidence_not_promoted | script/get-discussions |
| get-me | code_execution | cli_command | 0.650 | low_confidence_not_promoted | script/get-me |
| licenses | code_execution | cli_command | 0.650 | low_confidence_not_promoted | script/licenses |
| licenses-check | code_execution | cli_command | 0.650 | low_confidence_not_promoted | script/licenses-check |
| list-scopes | code_execution | cli_command | 0.650 | low_confidence_not_promoted | script/list-scopes |
| prettyprint-log | code_execution | cli_command | 0.650 | low_confidence_not_promoted | script/prettyprint-log |
| tag-release | code_execution | cli_command | 0.650 | low_confidence_not_promoted | script/tag-release |

## Repo: modelcontextprotocol/servers

Total extracted: 1  
Total deduped: 1  
Total promoted: 1  
Total skipped: 0

### Promoted tools

| Name | Capability Category | Execution Kind | Confidence | Promotion Reason | Source Path |
| --- | --- | --- | --- | --- | --- |
| fetch | structured_data | python_function | 0.820 | args_schema_strong_promoted | src/fetch/src/mcp_server_fetch/server.py |

### Skipped tools

_None skipped._

