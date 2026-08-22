// SPDX-License-Identifier: MIT
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/input-event-codes.h>
#include <linux/uinput.h>
#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

struct bridge {
	int fd;
	bool dry_run;
	bool trigger;
	bool grip;
	bool ax;
	bool by;
	bool system;
	bool stick_click;
	bool left_down;
	bool right_down;
	bool middle_down;
	bool escape_down;
};

static void
emit(struct bridge *bridge, unsigned short type, unsigned short code, int value)
{
	if (bridge->dry_run) {
		const char *name = type == EV_REL ? (code == REL_X ? "REL_X" : "REL_Y")
		                                  : (code == BTN_LEFT   ? "BTN_LEFT"
		                                     : code == BTN_RIGHT ? "BTN_RIGHT"
		                                     : code == BTN_MIDDLE ? "BTN_MIDDLE"
		                                                          : "KEY_ESC");
		printf("%s %d\n", name, value);
		return;
	}
	struct input_event event = {.type = type, .code = code, .value = value};
	if (write(bridge->fd, &event, sizeof(event)) != (ssize_t)sizeof(event)) {
		perror("oculus-controller-uinput: write");
		exit(1);
	}
}

static void
sync_events(struct bridge *bridge)
{
	if (bridge->dry_run) {
		puts("SYN");
		fflush(stdout);
		return;
	}
	emit(bridge, EV_SYN, SYN_REPORT, 0);
}

static void
update_key(struct bridge *bridge, bool value, bool *previous, unsigned short code, bool *changed)
{
	if (value == *previous) {
		return;
	}
	*previous = value;
	emit(bridge, EV_KEY, code, value ? 1 : 0);
	*changed = true;
}

static bool
hysteresis(float value, bool previous)
{
	return previous ? value >= 0.45f : value >= 0.65f;
}

static void
parse_line(struct bridge *bridge, const char *line)
{
	float x, y, fore, grip;
	int ax, by, system, stick_click;
	if (sscanf(line, " thumbstick : {x:%f, y:%f}", &x, &y) == 2) {
		if (!isfinite(x) || !isfinite(y)) {
			return;
		}
		const float deadzone = 0.20f;
		int relative_x = fabsf(x) > deadzone ? (int)lroundf(x * 18.0f) : 0;
		int relative_y = fabsf(y) > deadzone ? (int)lroundf(-y * 18.0f) : 0;
		if (relative_x != 0) {
			emit(bridge, EV_REL, REL_X, relative_x);
		}
		if (relative_y != 0) {
			emit(bridge, EV_REL, REL_Y, relative_y);
		}
		if (relative_x != 0 || relative_y != 0) {
			sync_events(bridge);
		}
		return;
	}
	if (sscanf(line, " trig : {fore:%f, grip:%f}", &fore, &grip) == 2) {
		if (!isfinite(fore) || !isfinite(grip)) {
			return;
		}
		bridge->trigger = hysteresis(fore, bridge->trigger);
		bridge->grip = hysteresis(grip, bridge->grip);
	} else if (sscanf(line, " button : {ax:%i, by:%i, sys:%i, ts:%i}", &ax, &by, &system,
	                  &stick_click) == 4) {
		bridge->ax = ax != 0;
		bridge->by = by != 0;
		bridge->system = system != 0;
		bridge->stick_click = stick_click != 0;
	} else {
		return;
	}

	bool changed = false;
	update_key(bridge, bridge->trigger || bridge->ax, &bridge->left_down, BTN_LEFT, &changed);
	update_key(bridge, bridge->grip || bridge->by, &bridge->right_down, BTN_RIGHT, &changed);
	update_key(bridge, bridge->stick_click, &bridge->middle_down, BTN_MIDDLE, &changed);
	update_key(bridge, bridge->system, &bridge->escape_down, KEY_ESC, &changed);
	if (changed) {
		sync_events(bridge);
	}
}

static int
create_device(const char *name)
{
	int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0) {
		perror("oculus-controller-uinput: open /dev/uinput");
		return -1;
	}
	if (ioctl(fd, UI_SET_EVBIT, EV_KEY) < 0 || ioctl(fd, UI_SET_KEYBIT, BTN_LEFT) < 0 ||
	    ioctl(fd, UI_SET_KEYBIT, BTN_RIGHT) < 0 || ioctl(fd, UI_SET_KEYBIT, BTN_MIDDLE) < 0 ||
	    ioctl(fd, UI_SET_KEYBIT, KEY_ESC) < 0 || ioctl(fd, UI_SET_EVBIT, EV_REL) < 0 ||
	    ioctl(fd, UI_SET_RELBIT, REL_X) < 0 || ioctl(fd, UI_SET_RELBIT, REL_Y) < 0) {
		perror("oculus-controller-uinput: configure");
		close(fd);
		return -1;
	}
	struct uinput_setup setup = {0};
	setup.id.bustype = BUS_BLUETOOTH;
	setup.id.vendor = 0x2833;
	setup.id.product = 0x0001;
	snprintf(setup.name, sizeof(setup.name), "%s", name);
	if (ioctl(fd, UI_DEV_SETUP, &setup) < 0 || ioctl(fd, UI_DEV_CREATE) < 0) {
		perror("oculus-controller-uinput: create");
		close(fd);
		return -1;
	}
	return fd;
}

int
main(int argc, char **argv)
{
	bool dry_run = argc == 2 && strcmp(argv[1], "--dry-run") == 0;
	if (argc > 2 || (argc == 2 && !dry_run)) {
		fprintf(stderr, "usage: oculus-controller-uinput [--dry-run]\n");
		return 2;
	}
	struct bridge bridge = {.fd = -1, .dry_run = dry_run};
	if (!dry_run) {
		bridge.fd = create_device("Oculus Touch desktop pointer");
		if (bridge.fd < 0) {
			return 1;
		}
	}
	char line[512];
	while (fgets(line, sizeof(line), stdin) != NULL) {
		parse_line(&bridge, line);
	}
	if (bridge.fd >= 0) {
		ioctl(bridge.fd, UI_DEV_DESTROY);
		close(bridge.fd);
	}
	return ferror(stdin) ? 1 : 0;
}
