// SPDX-License-Identifier: GPL-3.0-or-later
#include "gtklock-module.h"
#include "oculus-pattern-core.h"

#include <math.h>

#define MODULE_DATA(window) ((struct pattern_ui *)(window)->module_data[self_id])

const gchar module_name[] = "oculus-pattern";
const guint module_major_version = 4;
const guint module_minor_version = 0;

static int self_id;

struct pattern_ui {
	struct Window *window;
	GtkWidget *area;
	GtkWidget *recovery;
	struct oculus_pattern pattern;
	gboolean drawing;
	guint recovery_timeout;
};

static void
node_position(unsigned int node, double width, double height, double *x, double *y)
{
	*x = width * (0.2 + 0.3 * (node % 3));
	*y = height * (0.2 + 0.3 * (node / 3));
}

static int
hit_node(GtkWidget *widget, double x, double y)
{
	double width = gtk_widget_get_allocated_width(widget);
	double height = gtk_widget_get_allocated_height(widget);
	double radius = MIN(width, height) * 0.11;
	for (unsigned int node = 0; node < 9; node++) {
		double nx, ny;
		node_position(node, width, height, &nx, &ny);
		if (hypot(x - nx, y - ny) <= radius) {
			return (int)node;
		}
	}
	return -1;
}

static gboolean
draw_pattern(GtkWidget *widget, cairo_t *cr, gpointer data)
{
	struct pattern_ui *ui = data;
	double width = gtk_widget_get_allocated_width(widget);
	double height = gtk_widget_get_allocated_height(widget);
	cairo_set_line_width(cr, 12.0);
	cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
	cairo_set_source_rgba(cr, 0.22, 0.68, 1.0, 0.85);
	for (size_t i = 1; i < ui->pattern.length; i++) {
		double x1, y1, x2, y2;
		node_position(ui->pattern.path[i - 1], width, height, &x1, &y1);
		node_position(ui->pattern.path[i], width, height, &x2, &y2);
		cairo_move_to(cr, x1, y1);
		cairo_line_to(cr, x2, y2);
		cairo_stroke(cr);
	}
	for (unsigned int node = 0; node < 9; node++) {
		double x, y;
		node_position(node, width, height, &x, &y);
		cairo_arc(cr, x, y, 28.0, 0.0, 2.0 * G_PI);
		if (ui->pattern.selected[node]) {
			cairo_set_source_rgb(cr, 0.22, 0.68, 1.0);
			cairo_fill(cr);
		} else {
			cairo_set_line_width(cr, 7.0);
			cairo_set_source_rgba(cr, 0.9, 0.94, 1.0, 0.9);
			cairo_stroke(cr);
		}
	}
	return FALSE;
}

static void
add_pointer_node(struct pattern_ui *ui, double x, double y)
{
	int node = hit_node(ui->area, x, y);
	if (node >= 0 && oculus_pattern_add(&ui->pattern, (unsigned int)node)) {
		gtk_widget_queue_draw(ui->area);
	}
}

static gboolean
press(GtkWidget *widget, GdkEventButton *event, gpointer data)
{
	(void)widget;
	struct pattern_ui *ui = data;
	if (event->button != GDK_BUTTON_PRIMARY ||
	    !gtk_widget_get_sensitive(ui->window->input_field)) {
		return FALSE;
	}
	oculus_pattern_reset(&ui->pattern);
	ui->drawing = TRUE;
	add_pointer_node(ui, event->x, event->y);
	return TRUE;
}

static gboolean
motion(GtkWidget *widget, GdkEventMotion *event, gpointer data)
{
	(void)widget;
	struct pattern_ui *ui = data;
	if (ui->drawing) {
		add_pointer_node(ui, event->x, event->y);
	}
	return ui->drawing;
}

static gboolean
release(GtkWidget *widget, GdkEventButton *event, gpointer data)
{
	(void)widget;
	struct pattern_ui *ui = data;
	if (event->button != GDK_BUTTON_PRIMARY || !ui->drawing) {
		return FALSE;
	}
	ui->drawing = FALSE;
	add_pointer_node(ui, event->x, event->y);
	if (oculus_pattern_valid(&ui->pattern)) {
		char password[10];
		oculus_pattern_password(&ui->pattern, password);
		gtk_entry_set_text(GTK_ENTRY(ui->window->input_field), password);
		g_signal_emit_by_name(ui->window->input_field, "activate");
	} else {
		gtk_label_set_text(GTK_LABEL(ui->window->error_label), "Connect at least four dots");
	}
	oculus_pattern_reset(&ui->pattern);
	gtk_widget_queue_draw(ui->area);
	return TRUE;
}

static gboolean
reset_recovery(gpointer data)
{
	struct pattern_ui *ui = data;
	gtk_button_set_label(GTK_BUTTON(ui->recovery), "Reboot to bootloader");
	ui->recovery_timeout = 0;
	return G_SOURCE_REMOVE;
}

static void
recovery_clicked(GtkButton *button, gpointer data)
{
	struct pattern_ui *ui = data;
	if (ui->recovery_timeout == 0) {
		gtk_button_set_label(button, "Press again to confirm bootloader reboot");
		ui->recovery_timeout = g_timeout_add_seconds(5, reset_recovery, ui);
		return;
	}
	g_source_remove(ui->recovery_timeout);
	ui->recovery_timeout = 0;
	g_spawn_command_line_async("sudo -n /usr/sbin/oculus-reboot-bootloader", NULL);
}

void
on_activation(struct GtkLock *gtklock, int id)
{
	(void)gtklock;
	self_id = id;
}

void
on_window_create(struct GtkLock *gtklock, struct Window *window)
{
	(void)gtklock;
	struct pattern_ui *ui = g_new0(struct pattern_ui, 1);
	window->module_data[self_id] = ui;
	ui->window = window;
	ui->area = gtk_drawing_area_new();
	gtk_widget_set_size_request(ui->area, 520, 520);
	gtk_widget_set_name(ui->area, "oculus-pattern");
	gtk_widget_add_events(ui->area, GDK_BUTTON_PRESS_MASK | GDK_BUTTON_RELEASE_MASK |
	                                GDK_POINTER_MOTION_MASK);
	g_signal_connect(ui->area, "draw", G_CALLBACK(draw_pattern), ui);
	g_signal_connect(ui->area, "button-press-event", G_CALLBACK(press), ui);
	g_signal_connect(ui->area, "motion-notify-event", G_CALLBACK(motion), ui);
	g_signal_connect(ui->area, "button-release-event", G_CALLBACK(release), ui);
	gtk_grid_attach(GTK_GRID(window->body_grid), ui->area, 0, 3, 3, 1);

	ui->recovery = gtk_button_new_with_label("Reboot to bootloader");
	gtk_widget_set_name(ui->recovery, "oculus-recovery-button");
	g_signal_connect(ui->recovery, "clicked", G_CALLBACK(recovery_clicked), ui);
	gtk_grid_attach(GTK_GRID(window->body_grid), ui->recovery, 0, 4, 2, 1);
	gtk_widget_show_all(window->body_grid);
}

void
on_window_destroy(struct GtkLock *gtklock, struct Window *window)
{
	(void)gtklock;
	struct pattern_ui *ui = MODULE_DATA(window);
	if (ui == NULL) {
		return;
	}
	if (ui->recovery_timeout != 0) {
		g_source_remove(ui->recovery_timeout);
	}
	g_free(ui);
	window->module_data[self_id] = NULL;
}
