#!/bin/sh
# Focused ARM64/Linux checks against the actual DAWN telemetry implementation.
set -eu
cd "$(dirname "$0")"
dawn=../dawn
build=$(mktemp -d /tmp/backpack-stat-tests.XXXXXX)
trap 'rm -rf "$build"' EXIT
cc -std=gnu11 -Wall -Wextra -Werror -DUNITY_INCLUDE_DOUBLE \
  -I"$dawn/include" -I"$dawn/common/include" -I"$dawn/tests" -I"$dawn/third_party/unity" \
  "$dawn/tests/test_stat_service.c" "$dawn/src/core/stat_service.c" \
  "$dawn/src/core/stat_db.c" "$dawn/src/core/stat_net_interpret.c" \
  "$dawn/src/core/path_utils.c" "$dawn/src/tools/stat_render.c" \
  "$dawn/common/src/logging.c" "$dawn/common/src/utils/string_utils.c" \
  "$dawn/third_party/unity/unity.c" -ljson-c -lsqlite3 -lpthread -lm -o "$build/stat"
"$build/stat"
cc -std=gnu11 -Wall -Wextra -Werror -DUNITY_INCLUDE_DOUBLE \
  -I"$dawn/include" -I"$dawn/common/include" -I"$dawn/third_party/unity" \
  "$dawn/tests/test_attention_gate.c" "$dawn/src/core/attention/attention_gate.c" \
  "$dawn/src/core/attention/attention_policy.c" "$dawn/src/core/attention/attention_catalog.c" \
  "$dawn/third_party/unity/unity.c" -lm -o "$build/attention"
"$build/attention"
cc -std=gnu11 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
  -I"$dawn/include" -I"$dawn/common/include" \
  test_backpack_ack.c "$dawn/src/core/backpack_runtime.c" \
  "$dawn/src/core/wake_word.c" "$dawn/common/src/logging.c" \
  -Wl,--gc-sections -ljson-c -lsodium -lpthread -lm -o "$build/continuity"
"$build/continuity"
cc -std=gnu11 -Wall -Wextra -Werror \
  -I"$dawn/include" -I"$dawn/common/include" \
  replay_stat.c "$dawn/src/core/stat_service.c" "$dawn/src/core/stat_db.c" \
  "$dawn/src/core/stat_net_interpret.c" "$dawn/src/core/path_utils.c" \
  "$dawn/src/tools/stat_render.c" "$dawn/common/src/logging.c" \
  "$dawn/common/src/utils/string_utils.c" -ljson-c -lsqlite3 -lpthread -lm -o "$build/replay"
BACKPACK_STAT_REPLAY="$build/replay" python3 -B -m unittest discover -s . -p 'test_*.py' -v
