/*
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 * By contributing to this project, you agree to license your contributions
 * under the GPLv3 (or any later version) or any future licenses chosen by
 * the project author(s). Contributions include any modifications,
 * enhancements, or additions to the project. These contributions become
 * part of the project and are adopted by the project author(s).
 *
 * Backpack durable state and power-verification runtime bridge.
 */
#ifndef BACKPACK_RUNTIME_H
#define BACKPACK_RUNTIME_H

#include <json-c/json.h>

#include "core/session_manager.h"

/* Opt-in via DAWN_BACKPACK_SOCKET; no effect in ordinary DAWN installations. */
struct json_object *backpack_runtime_request(struct json_object *request);
void backpack_history_save(session_t *session);
void backpack_history_restore(session_t *session);
bool backpack_should_greet(void);
void backpack_watchdog_tick(void);
void backpack_notice_tick(void);
void backpack_notice_stop(void);
int backpack_power_tool_register(void);
int backpack_camera_tool_register(void);
int backpack_host_tools_register(void);
bool backpack_handle_host_command(session_t *session, const char *text);
void backpack_acknowledge_request(const char *text);
bool backpack_camera_is_request(const char *text);
char *backpack_camera_describe(const char *query);
const char *backpack_drone_action(const char *text);
char *backpack_drone_request(const char *action, const char *query);
int backpack_drone_tool_register(void);
bool backpack_handle_battery_command(session_t *session, const char *text);
bool backpack_handle_power_command(session_t *session, const char *text);

#endif
