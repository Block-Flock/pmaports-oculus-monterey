// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <stdbool.h>
#include <stddef.h>

struct oculus_pattern {
	unsigned char path[9];
	bool selected[9];
	size_t length;
};

void oculus_pattern_reset(struct oculus_pattern *pattern);
bool oculus_pattern_add(struct oculus_pattern *pattern, unsigned int node);
bool oculus_pattern_valid(const struct oculus_pattern *pattern);
void oculus_pattern_password(const struct oculus_pattern *pattern, char password[10]);
