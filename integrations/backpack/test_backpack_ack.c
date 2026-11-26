/* Link the actual native acknowledgment path; speech is replaced by a collector. */
#include <assert.h>
#include <pthread.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include "core/backpack_runtime.h"

static char spoken[256];
static int calls;
static uint32_t draws;

/* Drive each possible random selection without a probabilistic coverage test. */
uint32_t randombytes_uniform(uint32_t upper_bound) {
   assert(upper_bound == 8);
   return draws++ % upper_bound;
}

void text_to_speech(const char *text) {
   snprintf(spoken, sizeof(spoken), "%s", text);
   calls++;
}

struct recon_reply {
   int listener;
   const char *operation;
   const char *reply;
};

static void *reply_to_recon(void *argument) {
   struct recon_reply *fixture = argument;
   int client = accept(fixture->listener, NULL, NULL);
   assert(client >= 0);
   char buffer[4096];
   size_t used = 0;
   while (used < sizeof(buffer) - 1) {
      ssize_t count = read(client, buffer + used, sizeof(buffer) - 1 - used);
      assert(count > 0);
      used += (size_t)count;
      if (memchr(buffer, '\n', used))
         break;
   }
   buffer[used] = '\0';
   struct json_object *request = json_tokener_parse(buffer);
   assert(request);
   assert(!strcmp(json_object_get_string(json_object_object_get(request, "operation")),
                  fixture->operation));
   json_object_put(request);
   size_t length = strlen(fixture->reply), sent = 0;
   while (sent < length) {
      ssize_t count = write(client, fixture->reply + sent, length - sent);
      assert(count > 0);
      sent += (size_t)count;
   }
   close(client);
   return NULL;
}

static void check_watchdog(bool abstract) {
   char directory[] = "/tmp/backpack-watchdog-test.XXXXXX";
   assert(mkdtemp(directory));
   struct sockaddr_un address = { .sun_family = AF_UNIX };
   char path[sizeof(address.sun_path)];
   snprintf(path, sizeof(path), "%s%s/notify", abstract ? "@" : "", directory);
   snprintf(address.sun_path, sizeof(address.sun_path), "%s", path);
   size_t length = strlen(path);
   if (abstract) {
      address.sun_path[0] = '\0';
   }
   int listener = socket(AF_UNIX, SOCK_DGRAM, 0);
   assert(listener >= 0);
   struct timeval timeout = { .tv_sec = 2 };
   setsockopt(listener, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
   assert(bind(listener, (struct sockaddr *)&address,
               offsetof(struct sockaddr_un, sun_path) + length + (abstract ? 0 : 1)) == 0);
   setenv("NOTIFY_SOCKET", path, 1);
   backpack_watchdog_tick();
   char buffer[128] = { 0 };
   assert(recv(listener, buffer, sizeof(buffer) - 1, 0) > 0);
   assert(!strcmp(buffer, "READY=1\nWATCHDOG=1"));
   close(listener);
   if (!abstract) {
      unlink(path);
   }
   rmdir(directory);
   unsetenv("NOTIFY_SOCKET");
}

static void check_startup_handoff(void) {
   unsetenv("DAWN_BACKPACK_SOCKET");
   assert(backpack_should_greet());
   char directory[] = "/tmp/backpack-startup-test.XXXXXX";
   assert(mkdtemp(directory));
   struct sockaddr_un address = { .sun_family = AF_UNIX };
   snprintf(address.sun_path, sizeof(address.sun_path), "%s/runtime.sock", directory);
   int listener = socket(AF_UNIX, SOCK_STREAM, 0);
   assert(listener >= 0);
   assert(bind(listener, (struct sockaddr *)&address, sizeof(address)) == 0);
   assert(listen(listener, 1) == 0);
   setenv("DAWN_BACKPACK_SOCKET", address.sun_path, 1);
   struct recon_reply fixture = { listener, "dawn_startup", "{\"skip_greeting\":true}\n" };
   pthread_t thread;
   assert(pthread_create(&thread, NULL, reply_to_recon, &fixture) == 0);
   assert(!backpack_should_greet());
   pthread_join(thread, NULL);
   close(listener);
   unlink(address.sun_path);
   rmdir(directory);
}

static void check_recon_response(const char *action,
                                 const char *operation,
                                 const char *reply,
                                 const char *expected) {
   char directory[] = "/tmp/backpack-recon-test.XXXXXX";
   assert(mkdtemp(directory));
   struct sockaddr_un address = { .sun_family = AF_UNIX };
   snprintf(address.sun_path, sizeof(address.sun_path), "%s/runtime.sock", directory);
   int listener = socket(AF_UNIX, SOCK_STREAM, 0);
   assert(listener >= 0);
   assert(bind(listener, (struct sockaddr *)&address, sizeof(address)) == 0);
   assert(listen(listener, 1) == 0);
   setenv("DAWN_BACKPACK_SOCKET", address.sun_path, 1);
   struct recon_reply fixture = { listener, operation, reply };
   pthread_t worker;
   assert(pthread_create(&worker, NULL, reply_to_recon, &fixture) == 0);
   char *text = backpack_drone_request(action, "test");
   assert(text && strstr(text, expected));
   free(text);
   assert(pthread_join(worker, NULL) == 0);
   close(listener);
   unlink(address.sun_path);
   rmdir(directory);
}

int main(void) {
   check_watchdog(false);
   check_watchdog(true);
   check_startup_handoff();
   unsetenv("DAWN_BACKPACK_SOCKET");
   assert(backpack_drone_action("start ASTRA") == NULL);
   backpack_acknowledge_request("what is the uptime");
   assert(calls == 0);
   setenv("DAWN_BACKPACK_SOCKET", "/nonexistent-test-socket", 1);
   assert(!strcmp(backpack_drone_action("Start ASTRA."), "start"));
   assert(!strcmp(backpack_drone_action("What's on the eye in the sky?"), "describe"));
   assert(!strcmp(backpack_drone_action("What's on the iron sky?"), "describe"));
   assert(!strcmp(backpack_drone_action("What on the eye in the sky?"), "describe"));
   assert(!strcmp(backpack_drone_action(" What's on the eye in the sky?  "), "describe"));
   assert(!strcmp(backpack_drone_action(" Initiate ASTRA mode. "), "start"));
   assert(!strcmp(backpack_drone_action(" Initiate drone recon. "), "start"));
   assert(!strcmp(backpack_drone_action("Terminate drone recon!"), "stop"));
   assert(!strcmp(backpack_drone_action(" Start recon mode. "), "start"));
   assert(!strcmp(backpack_drone_action("Stop recon mode!"), "stop"));
   assert(backpack_drone_action("how do I stop recon mode") == NULL);
   assert(!strcmp(backpack_drone_action("Drone recon status?"), "status"));
   assert(backpack_drone_action("how do I terminate drone recon") == NULL);
   assert(backpack_drone_action("what do you see") == NULL);
   assert(backpack_drone_action("explain how to start the drone feed") == NULL);
   const char *names[] = { "ASTRA", "recon", "Icarus" };
   const char *verbs[] = { "start", "initiate", "stop", "terminate" };
   char phrase[128];
   for (size_t n = 0; n < 3; n++) {
      for (size_t v = 0; v < 4; v++) {
         snprintf(phrase, sizeof(phrase), " %s %s! ", verbs[v], names[n]);
         assert(!strcmp(backpack_drone_action(phrase), v < 2 ? "start" : "stop"));
         snprintf(phrase, sizeof(phrase), "%s %s mode", verbs[v], names[n]);
         assert(!strcmp(backpack_drone_action(phrase), v < 2 ? "start" : "stop"));
      }
      snprintf(phrase, sizeof(phrase), "%s stats", names[n]);
      assert(!strcmp(backpack_drone_action(phrase), "status"));
      snprintf(phrase, sizeof(phrase), "%s mode status", names[n]);
      assert(!strcmp(backpack_drone_action(phrase), "status"));
      snprintf(phrase, sizeof(phrase), "What's the %s status?", names[n]);
      assert(!strcmp(backpack_drone_action(phrase), "status"));
   }
   assert(backpack_drone_action("start Astro") == NULL);
   assert(backpack_drone_action("start Hermes mode") == NULL);
   assert(backpack_drone_action("start Sentinel") == NULL);
   assert(backpack_drone_action("what is ASTRA") == NULL);
   assert(backpack_drone_action("how do I start ASTRA") == NULL);
   assert(backpack_drone_action("don't stop Icarus mode") == NULL);
   assert(backpack_drone_action("pull up the drone feed") == NULL);
   assert(draws == 0);
   static const char *const expected[] = {
      "Checking that now.",      "Taking a look.",   "On it.",
      "Let me check.",           "One moment.",      "Let me look into that.",
      "I'll check the details.", "Give me a moment."
   };
   for (size_t i = 0; i < sizeof(expected) / sizeof(expected[0]); i++) {
      backpack_acknowledge_request(i % 2 ? "Are you seeing this?" : "What is the memory usage?");
      assert(calls == (int)i + 1 && !strcmp(spoken, expected[i]));
   }
   backpack_acknowledge_request("cancel");
   backpack_acknowledge_request("yes");
   backpack_acknowledge_request("confirm");
   backpack_acknowledge_request(NULL);
   assert(calls == 8 && draws == 8);
   check_recon_response("start", "drone_start",
                        "{\"description\":\"Ready\",\"source\":\"goggles3\",\"fresh\":true}\n",
                        "Ready");
   check_recon_response("start", "drone_start",
                        "{\"description\":\"Ready\",\"source\":\"goggles3\",\"fresh\":false}\n",
                        "couldn't");
   check_recon_response(
       "stop", "drone_stop",
       "{\"description\":\"Recon terminated\",\"source\":\"goggles3\",\"fresh\":false}\n",
       "terminated");
   check_recon_response(
       "status", "drone_status",
       "{\"description\":\"Recon stopped\",\"source\":\"goggles3\",\"fresh\":false}\n", "stopped");
   check_recon_response("describe", "drone_describe",
                        "{\"description\":\"Wrong source\",\"source\":\"camera\",\"fresh\":true}\n",
                        "couldn't");
   puts("All eight random cue selections and suppression cases passed; no real speech or host "
        "actions.");
   return 0;
}
