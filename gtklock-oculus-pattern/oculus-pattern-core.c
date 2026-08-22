// SPDX-License-Identifier: GPL-3.0-or-later
#include "oculus-pattern-core.h"

#include <string.h>

void
oculus_pattern_reset(struct oculus_pattern *pattern)
{
	memset(pattern, 0, sizeof(*pattern));
}

static void
append(struct oculus_pattern *pattern, unsigned int node)
{
	pattern->path[pattern->length++] = (unsigned char)node;
	pattern->selected[node] = true;
}

bool
oculus_pattern_add(struct oculus_pattern *pattern, unsigned int node)
{
	if (node >= 9 || pattern->selected[node] || pattern->length >= 9) {
		return false;
	}
	if (pattern->length > 0) {
		unsigned int previous = pattern->path[pattern->length - 1];
		int previous_x = (int)(previous % 3);
		int previous_y = (int)(previous / 3);
		int node_x = (int)(node % 3);
		int node_y = (int)(node / 3);
		if (((previous_x + node_x) % 2) == 0 && ((previous_y + node_y) % 2) == 0) {
			unsigned int middle = (unsigned int)(((previous_y + node_y) / 2) * 3 +
			                                     (previous_x + node_x) / 2);
			if (middle != previous && middle != node && !pattern->selected[middle]) {
				append(pattern, middle);
			}
		}
	}
	append(pattern, node);
	return true;
}

bool
oculus_pattern_valid(const struct oculus_pattern *pattern)
{
	return pattern->length >= 4;
}

void
oculus_pattern_password(const struct oculus_pattern *pattern, char password[10])
{
	for (size_t i = 0; i < pattern->length; i++) {
		password[i] = (char)('1' + pattern->path[i]);
	}
	password[pattern->length] = '\0';
}
