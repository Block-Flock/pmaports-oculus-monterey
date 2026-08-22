/* SPDX-License-Identifier: MIT */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define DEFAULT_DEVICE "/dev/syncboss_stream0"
#define DEFAULT_PACKETS 8U
#define DEFAULT_TIMEOUT_MS 2000
#define MAX_RECORD_SIZE 255U

static void
usage(const char *name)
{
	fprintf(stderr,
	        "usage: %s [-d DEVICE] [-n PACKETS] [-t TIMEOUT_MS]\n"
	        "Read and hex-dump SyncBoss stream records without writing to the MCU.\n",
	        name);
}

static int
parse_u32(const char *text, unsigned int *value)
{
	char *end = NULL;
	unsigned long parsed;

	errno = 0;
	parsed = strtoul(text, &end, 10);
	if (errno != 0 || text[0] == '\0' || *end != '\0' || parsed > UINT32_MAX)
		return -1;
	*value = (unsigned int)parsed;
	return 0;
}

static void
dump_record(unsigned int sequence, const uint8_t *data, size_t length)
{
	size_t i;

	printf("record=%u length=%zu", sequence, length);
	if (length >= 3)
		printf(" header_version=%u header_length=%u from_driver=%u",
		       data[0], data[1], data[2] != 0);
	putchar('\n');

	for (i = 0; i < length; i++) {
		if (i % 16 == 0)
			printf("%04zx:", i);
		printf(" %02x", data[i]);
		if (i % 16 == 15 || i + 1 == length)
			putchar('\n');
	}
}

int
main(int argc, char **argv)
{
	const char *device = DEFAULT_DEVICE;
	unsigned int packets = DEFAULT_PACKETS;
	unsigned int timeout = DEFAULT_TIMEOUT_MS;
	uint8_t record[MAX_RECORD_SIZE];
	unsigned int captured = 0;
	int option;
	int fd;

	while ((option = getopt(argc, argv, "d:n:t:h")) != -1) {
		switch (option) {
		case 'd':
			device = optarg;
			break;
		case 'n':
			if (parse_u32(optarg, &packets) != 0 || packets == 0) {
				usage(argv[0]);
				return 2;
			}
			break;
		case 't':
			if (parse_u32(optarg, &timeout) != 0 || timeout > INT32_MAX) {
				usage(argv[0]);
				return 2;
			}
			break;
		default:
			usage(argv[0]);
			return option == 'h' ? 0 : 2;
		}
	}
	if (optind != argc) {
		usage(argv[0]);
		return 2;
	}

	/* O_RDONLY is a deliberate safety boundary: this tool cannot command,
	 * reset, pair, or update the SyncBoss MCU or either controller. */
	fd = open(device, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0) {
		fprintf(stderr, "cannot open %s read-only: %s\n", device, strerror(errno));
		return 1;
	}

	while (captured < packets) {
		struct pollfd ready = {.fd = fd, .events = POLLIN};
		ssize_t length;
		int result = poll(&ready, 1, (int)timeout);

		if (result == 0) {
			fprintf(stderr, "timeout waiting for SyncBoss record (%u/%u captured)\n",
			        captured, packets);
			close(fd);
			return 3;
		}
		if (result < 0) {
			if (errno == EINTR)
				continue;
			fprintf(stderr, "poll failed: %s\n", strerror(errno));
			close(fd);
			return 1;
		}
		if ((ready.revents & (POLLERR | POLLHUP | POLLNVAL)) != 0) {
			fprintf(stderr, "SyncBoss stream became unavailable (poll=0x%x)\n",
			        ready.revents);
			close(fd);
			return 1;
		}

		length = read(fd, record, sizeof(record));
		if (length < 0 && (errno == EAGAIN || errno == EINTR))
			continue;
		if (length <= 0) {
			fprintf(stderr, "SyncBoss read failed: %s\n",
			        length == 0 ? "end of stream" : strerror(errno));
			close(fd);
			return 1;
		}

		dump_record(++captured, record, (size_t)length);
	}

	close(fd);
	return 0;
}
