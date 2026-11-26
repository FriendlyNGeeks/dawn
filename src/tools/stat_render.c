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
 * the project author(s).
 *
 * STAT network-telemetry renderer (pure). See stat_render.h.
 */

#include "tools/stat_render.h"

#include <stdio.h>
#include <string.h>

#include "core/stat_net_interpret.h"

/* Append the honest reachability phrase for one interface's gateway probe. A
 * single reachable:false is a dropped packet, not an outage — only fail_streak
 * >= 2 reads as "down". */
static void append_reach_phrase(const stat_net_reach_t *re, char *buf, size_t sz) {
   if (!re) {
      return;
   }
   size_t off = strlen(buf);
   if (re->fail_streak >= 2) {
      snprintf(buf + off, sz - off, ", gateway unreachable (%d consecutive failures)",
               re->fail_streak);
   } else if (re->reachable) {
      if (re->has_rtt) {
         snprintf(buf + off, sz - off, ", gateway reachable (%.1f ms)", re->rtt_ms);
      } else {
         snprintf(buf + off, sz - off, ", gateway reachable");
      }
   } else {
      snprintf(buf + off, sz - off, ", gateway probe missed once (transient)");
   }
}

void stat_render_network(const stat_snapshot_t *s, char *buf, size_t sz) {
   if (!s->have_network) {
      size_t off = strlen(buf);
      snprintf(buf + off, sz - off, "No network telemetry from STAT. ");
      return;
   }

   const stat_net_route_t *r = stat_net_primary_route(s, NULL);
   size_t off = strlen(buf);
   if (r) {
      const stat_net_iface_t *pf = stat_net_iface_by_name(s, r->iface);
      const char *kind = (pf && pf->kind[0]) ? pf->kind : "";
      snprintf(buf + off, sz - off, "Network: primary path %s%s%s%s via %s. ", r->iface,
               kind[0] ? " (" : "", kind, kind[0] ? ")" : "", r->gateway);
   } else {
      snprintf(buf + off, sz - off, "Network: no default route. ");
   }

   for (int i = 0; i < s->net_iface_count; i++) {
      const stat_net_iface_t *f = &s->net_ifaces[i];
      bool linkup = f->up && f->carrier; /* trust up/carrier, not the operstate string */
      const stat_net_reach_t *re = stat_net_reach_for_iface(s, f->name);
      off = strlen(buf);
      snprintf(buf + off, sz - off, "%s (%s): %s%s%s", f->name, f->kind[0] ? f->kind : "?",
               linkup ? "up" : "down", f->ipv4[0] ? ", " : "", f->ipv4[0] ? f->ipv4 : "");
      append_reach_phrase(re, buf, sz);
      if (f->addr_truncated) {
         off = strlen(buf);
         snprintf(buf + off, sz - off, " (+more addresses)");
      }
      /* Cellular honesty: a gateway ping over the cellular iface proves the USB
       * link to the modem, NOT that the cellular bearer is carrying traffic. A
       * global IPv6 on the iface is the best available bearer-presence proxy.
       * Lead with the caveat so it survives any buffer truncation, not the
       * "likely active" hedge. */
      if (strcmp(f->kind, "cellular") == 0 && linkup) {
         off = strlen(buf);
         snprintf(buf + off, sz - off,
                  " (gateway reachability here is the USB link to the modem, not the cellular "
                  "bearer; %s)",
                  f->ipv6_global[0] ? "a global IPv6 is present, so the bearer is likely active"
                                    : "no global IPv6, so the bearer may be down");
      }
      off = strlen(buf);
      snprintf(buf + off, sz - off, ". ");
   }

   if (!s->net_probe_available) {
      off = strlen(buf);
      snprintf(buf + off, sz - off, "(Reachability probe unavailable — link state only.) ");
   }
   if (s->net_ifaces_truncated || s->net_routes_truncated || s->net_reach_truncated) {
      off = strlen(buf);
      snprintf(buf + off, sz - off, "(Some interfaces/routes/probes omitted.) ");
   }
}

static void fmt_duration_min(double minutes, char *out, size_t out_sz) {
   /* Upper-bound the cast: a huge (finite) time_remaining_min from a misbehaving
    * publisher would make (int)(minutes+0.5) an out-of-range double->int (UB).
    * 10,000,000 min (~19 years) is well past any real battery runtime. */
   if (minutes <= 0 || minutes > 10000000.0) {
      snprintf(out, out_sz, "unknown");
      return;
   }
   int total = (int)(minutes + 0.5);
   int h = total / 60, m = total % 60;
   if (h > 0) {
      snprintf(out, out_sz, "%dh %dm", h, m);
   } else {
      snprintf(out, out_sz, "%dm", m);
   }
}

/* Append a battery description to buf (bounded). */
void stat_render_battery(const stat_snapshot_t *s, char *buf, size_t sz) {
   size_t off = strlen(buf);
   if (!s->have_battery || s->battery_stale || !s->stat_online) {
      snprintf(buf + off, sz - off, "Battery data unavailable%s (last battery sample %ds ago). ",
               s->have_battery ? "/stale" : "", s->battery_age_sec);
      return;
   }
   if (s->battery_simulated) {
      snprintf(buf + off, sz - off, "SIMULATED battery telemetry. ");
   }
   char remain[32];
   fmt_duration_min(s->time_remaining_min, remain, sizeof(remain));
   char health[160];
   const char *st = s->battery_status[0] ? s->battery_status : "unknown";
   if (s->crit_faults > 0 || s->warn_faults > 0) {
      snprintf(health, sizeof(health), "health %s (%d critical, %d warning)%s%s", st,
               s->crit_faults, s->warn_faults, s->status_reason[0] ? ": " : "", s->status_reason);
   } else {
      snprintf(health, sizeof(health), "health %s", st);
   }
   off = strlen(buf);
   snprintf(buf + off, sz - off, "Battery %.0f%% (%.1f V, %.2f A, %.1f W)%s%s, ~%s remaining, %s. ",
            s->batt_level, s->batt_voltage, s->batt_current, s->batt_power,
            s->charging_state[0] ? ", " : "", s->charging_state, remain, health);
   for (int i = 0; i < s->battery_pack_count && i < STAT_BATTERY_MAX_PACKS; i++) {
      const stat_battery_pack_t *p = &s->battery_packs[i];
      off = strlen(buf);
      if (!p->present) {
         snprintf(buf + off, sz - off, "Slot %s: removed. ", p->id);
      } else {
         snprintf(buf + off, sz - off, "Slot %s: %.0f%%, %.1f V, %.2f A, %.1f W, %.1f C (%s). ",
                  p->id, p->level, p->voltage, p->current, p->power, p->temperature,
                  p->supplying ? "supplying" : "standby");
      }
   }
}

/* Short local speech uses the same freshness contract as the full tool. */
void stat_render_battery_brief(const stat_snapshot_t *s, char *buf, size_t sz) {
   if (!s->ever_seen || !s->stat_online || s->stale || !s->have_battery || s->battery_stale) {
      snprintf(buf, sz, "Current battery data is unavailable or stale.");
      return;
   }
   const char *health = s->crit_faults > 0 || !strcmp(s->battery_status, "CRITICAL")
                            ? " Critical battery warning."
                        : s->warn_faults > 0 || !strcmp(s->battery_status, "WARNING")
                            ? " Battery warning."
                            : "";
   snprintf(buf, sz, "%sBattery is at %.0f percent.%s",
            s->battery_simulated ? "Simulated reading. " : "", s->batt_level, health);
}