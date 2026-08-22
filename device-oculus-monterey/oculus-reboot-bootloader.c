#include <errno.h>
#include <linux/reboot.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static int usage(const char *program)
{
	fprintf(stderr, "usage: %s [--dry-run]\n", program);
	return 64;
}

int main(int argc, char **argv)
{
	static const char reason[] = "bootloader";

	if (argc == 2 && strcmp(argv[1], "--dry-run") == 0) {
		puts("restart2 reason=bootloader");
		return 0;
	}
	if (argc != 1)
		return usage(argv[0]);
	if (geteuid() != 0) {
		fputs("oculus-reboot-bootloader: root privileges required\n", stderr);
		return 77;
	}

	/* Flush the rootfs before asking the Qualcomm restart driver to set the
	 * PON bootloader reason and reset the headset. */
	sync();
	if (syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
		    LINUX_REBOOT_CMD_RESTART2, reason) == -1) {
		fprintf(stderr, "oculus-reboot-bootloader: reboot: %s\n",
			strerror(errno));
		return 1;
	}

	return 0;
}

