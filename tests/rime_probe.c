/* Isolated deployment and candidate probe using the public librime C API. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <rime_api.h>

int main(int argc, char **argv) {
  if (argc < 4) {
    fprintf(stderr, "usage: rime_probe SHARED USER deploy|query [SCHEMA KEYS OPTION=0|1 ...]\n");
    return 2;
  }
  RIME_STRUCT(RimeTraits, traits);
  traits.shared_data_dir = argv[1];
  traits.user_data_dir = argv[2];
  traits.app_name = "rime.govrime-test";
  traits.min_log_level = 2;
  traits.log_dir = "";
  RimeApi *api = rime_get_api();
  api->setup(&traits);
  api->initialize(&traits);
  if (strcmp(argv[3], "deploy") == 0) {
    api->deployer_initialize(&traits);
    int ok = api->deploy();
    printf("librime\t%s\n", api->get_version());
    api->finalize();
    return ok ? 0 : 1;
  }
  if (argc < 6 || strcmp(argv[3], "query") != 0) {
    api->finalize();
    return 2;
  }
  RimeSessionId session = api->create_session();
  if (!session || !api->select_schema(session, argv[4])) {
    fprintf(stderr, "cannot select schema: %s\n", argv[4]);
    api->finalize();
    return 1;
  }
  const char *options[] = {"traditionalization", "gov_traditional", "zh_hans", "zh_hant", "simplification", NULL};
  for (int i = 0; options[i]; i++)
    printf("default\t%s\t%d\n", options[i], api->get_option(session, options[i]));
  api->set_option(session, "ascii_mode", 0);
  for (int i = 6; i < argc; i++) {
    char *separator = strchr(argv[i], '=');
    if (!separator || (strcmp(separator + 1, "0") && strcmp(separator + 1, "1"))) {
      api->finalize();
      return 2;
    }
    *separator = '\0';
    api->set_option(session, argv[i], atoi(separator + 1));
  }
  if (!api->simulate_key_sequence(session, argv[5])) {
    fprintf(stderr, "key sequence rejected: %s\n", argv[5]);
    api->finalize();
    return 1;
  }
  RimeCandidateListIterator iterator = {0};
  int count = 0;
  if (api->candidate_list_begin(session, &iterator)) {
    while (count < 50 && api->candidate_list_next(&iterator)) {
      printf("candidate\t%s\n", iterator.candidate.text);
      count++;
    }
    api->candidate_list_end(&iterator);
  }
  api->destroy_session(session);
  api->finalize();
  return count ? 0 : 1;
}
