/* SPDX-License-Identifier: MIT */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
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
#define HMD_IMU_PACKET_TYPE 0x50U
#define HMD_IMU_PAYLOAD_SIZE 36U
#define STANDARD_GRAVITY 9.80665f
#define DEGREES_TO_RADIANS 0.017453292519943295f

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
decode_imu(const uint8_t *payload, size_t length)
{
	uint64_t timestamp;
	uint32_t metadata;
	float acceleration[3];
	float angular_velocity[3];
	unsigned int i;

	if (length < HMD_IMU_PAYLOAD_SIZE) {
		printf("imu truncated=yes expected=%u actual=%zu\n",
		       HMD_IMU_PAYLOAD_SIZE, length);
		return;
	}

	memcpy(&timestamp, payload, sizeof(timestamp));
	memcpy(acceleration, payload + 8, sizeof(acceleration));
	memcpy(angular_velocity, payload + 20, sizeof(angular_velocity));
	memcpy(&metadata, payload + 32, sizeof(metadata));

	for (i = 0; i < 3; i++) {
		acceleration[i] *= STANDARD_GRAVITY;
		angular_velocity[i] *= DEGREES_TO_RADIANS;
	}
	printf("imu timestamp=%" PRIu64 " metadata=0x%08" PRIx32
	       " accel_m_s2=%.9g,%.9g,%.9g gyro_rad_s=%.9g,%.9g,%.9g\n",
	       timestamp, metadata,
	       acceleration[0], acceleration[1], acceleration[2],
	       angular_velocity[0], angular_velocity[1], angular_velocity[2]);
}

static void
decode_packets(const uint8_t *data, size_t length)
{
	size_t offset;

	if (length < 3 || data[0] != 1 || data[1] < 3 || data[1] > length || data[2] != 0)
		return;

	offset = data[1];
	while (length - offset >= 3) {
		uint8_t type = data[offset];
		uint8_t sequence = data[offset + 1];
		uint8_t payload_length = data[offset + 2];
		size_t packet_length = (size_t)payload_length + 3;

		if (packet_length > length - offset) {
			printf("packet offset=%zu truncated=yes payload_length=%u remaining=%zu\n",
			       offset, payload_length, length - offset - 3);
			return;
		}
		printf("packet offset=%zu type=0x%02x sequence=%u payload_length=%u\n",
		       offset, type, sequence, payload_length);
		if (type == HMD_IMU_PACKET_TYPE)
			decode_imu(data + offset + 3, payload_length);
		offset += packet_length;
	}
	if (offset != length)
		printf("trailing_bytes=%zu\n", length - offset);
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
	decode_packets(data, length);
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
