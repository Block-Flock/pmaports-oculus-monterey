// SPDX-License-Identifier: GPL-3.0-or-later
#include "oculus-pattern-core.h"

#include <stdio.h>

int
main(void)
{
	struct oculus_pattern pattern = {0};
	int character;
	while ((character = getchar()) != EOF && character != '\n') {
		if (character < '1' || character > '9') {
			return 2;
		}
		(void)oculus_pattern_add(&pattern, (unsigned int)(character - '1'));
	}
	if (!oculus_pattern_valid(&pattern)) {
		return 2;
	}
	char password[10];
	oculus_pattern_password(&pattern, password);
	puts(password);
	return 0;
}
