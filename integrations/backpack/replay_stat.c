/* SPDX-License-Identifier: GPL-3.0-or-later
 * Offline integration harness: simulator envelopes -> real DAWN ingest/render.
 * No MQTT broker, model, hardware access, or persistent application database.
 */
#include <json-c/json.h>
#include <stdio.h>
#include <string.h>

#include "core/stat_service.h"
#include "tools/stat_render.h"

int main(int argc, char **argv) {
   if (argc != 2)
      return 1;
   stat_service_cfg_t cfg = { .enabled = true, .stale_after_sec = 1 };
   snprintf(cfg.telemetry_topic, sizeof(cfg.telemetry_topic), "backpack/sim/stat/telemetry");
   snprintf(cfg.status_topic, sizeof(cfg.status_topic), "backpack/sim/stat/status");
   snprintf(cfg.db_path, sizeof(cfg.db_path), "%s", argv[1]);
   if (stat_service_init(&cfg) != 0)
      return 1;
   char line[8192];
   int result = 0;
   while (fgets(line, sizeof(line), stdin)) {
      struct json_object *root = json_tokener_parse(line), *topic, *payload;
      if (!strchr(line, '\n') || !root || !json_object_is_type(root, json_type_object) ||
          !json_object_object_get_ex(root, "topic", &topic) ||
          !json_object_is_type(topic, json_type_string) ||
          !json_object_object_get_ex(root, "payload", &payload) ||
          !json_object_is_type(payload, json_type_object)) {
         if (root)
            json_object_put(root);
         result = 1;
         break;
      }
      const char *body = json_object_to_json_string(payload);
      if (!stat_service_handle_mqtt(json_object_get_string(topic), body, (int)strlen(body))) {
         json_object_put(root);
         result = 1;
         break;
      }
      json_object_put(root);
      stat_snapshot_t snapshot;
      stat_service_get_snapshot(&snapshot);
      char text[2048] = "";
      stat_render_battery(&snapshot, text, sizeof(text));
      printf("SNAPSHOT %s\n", text);
      fflush(stdout);
   }
   stat_service_shutdown();
   return result;
}
