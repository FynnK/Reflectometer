#pragma once

#include <cstring>
#include <cstdio>
#include <cstdlib>

struct Command {
    enum Type { NONE, START, STOP, SET, CONFIG, MONITOR };
    Type type = NONE;
    char mode[12] = "continuous";
    int enable = 0;
    int channels = 7;
    int osr = -1;
    int presamples = -1;
    int samples = -1;
    int pulse_ms = -1;
    int deadtime = -1;
    int brightness_r = -1;
    int brightness_b = -1;
    int brightness_g = -1;
    int send_raw = -1;
};

struct Config {
    int osr = 5;
    int presamples = 80;
    int samples = 160;
    int pulse_ms = 170;
    int channels = 7;  // bit0=R, bit1=B, bit2=G
    int deadtime = 3;  // samples discarded after LED on/off for settling
    int brightness[3] = {1000, 1000, 1000};  // R, B, G
    int send_raw = 0;  // 1 = stream raw ADC samples to host for software post-processing

    bool operator!=(const Config &o) const {
        return osr != o.osr || presamples != o.presamples ||
               samples != o.samples || pulse_ms != o.pulse_ms ||
               channels != o.channels || deadtime != o.deadtime ||
               brightness[0] != o.brightness[0] ||
               brightness[1] != o.brightness[1] ||
               brightness[2] != o.brightness[2] ||
               send_raw != o.send_raw;
    }
};

class Protocol {
public:
    static Command parse(const char *json) {
        Command cmd;
        char tmp[16] = {};
        if (!_scan_str(json, "cmd", tmp, sizeof(tmp))) return cmd;

        if (strcmp(tmp, "start") == 0) {
            cmd.type = Command::START;
            if (_scan_str(json, "mode", tmp, sizeof(tmp)))
                strncpy(cmd.mode, tmp, sizeof(cmd.mode) - 1);
            _scan_int(json, "osr", &cmd.osr);
            _scan_int(json, "presamples", &cmd.presamples);
            _scan_int(json, "samples", &cmd.samples);
            _scan_int(json, "pulse_ms", &cmd.pulse_ms);
            _scan_int(json, "channels", &cmd.channels);
            _scan_int(json, "deadtime", &cmd.deadtime);
            _scan_int(json, "brightness_r", &cmd.brightness_r);
            _scan_int(json, "brightness_b", &cmd.brightness_b);
            _scan_int(json, "brightness_g", &cmd.brightness_g);
            _scan_int(json, "send_raw", &cmd.send_raw);
            // fallback for old single "brightness" key
            if (cmd.brightness_r < 0 && cmd.brightness_b < 0 && cmd.brightness_g < 0) {
                int old = -1;
                if (_scan_int(json, "brightness", &old) && old >= 0)
                    cmd.brightness_r = cmd.brightness_b = cmd.brightness_g = old;
            }
        } else if (strcmp(tmp, "stop") == 0) {
            cmd.type = Command::STOP;
        } else if (strcmp(tmp, "set") == 0) {
            cmd.type = Command::SET;
            _scan_int(json, "osr", &cmd.osr);
            _scan_int(json, "presamples", &cmd.presamples);
            _scan_int(json, "samples", &cmd.samples);
            _scan_int(json, "pulse_ms", &cmd.pulse_ms);
            _scan_int(json, "channels", &cmd.channels);
            _scan_int(json, "deadtime", &cmd.deadtime);
            _scan_int(json, "brightness_r", &cmd.brightness_r);
            _scan_int(json, "brightness_b", &cmd.brightness_b);
            _scan_int(json, "brightness_g", &cmd.brightness_g);
            _scan_int(json, "send_raw", &cmd.send_raw);
            // fallback for old single "brightness" key
            if (cmd.brightness_r < 0 && cmd.brightness_b < 0 && cmd.brightness_g < 0) {
                int old = -1;
                if (_scan_int(json, "brightness", &old) && old >= 0)
                    cmd.brightness_r = cmd.brightness_b = cmd.brightness_g = old;
            }
        } else if (strcmp(tmp, "config") == 0) {
            cmd.type = Command::CONFIG;
        } else if (strcmp(tmp, "monitor") == 0) {
            cmd.type = Command::MONITOR;
            _scan_int(json, "enable", &cmd.enable);
        }
        return cmd;
    }

    static int format_data(char *buf, int size, const double ref[3], const double cur[3]) {
        return snprintf(buf, size,
            "{\"ev\":\"data\",\"r\":[%.4f,%.2f],\"b\":[%.4f,%.2f],\"g\":[%.4f,%.2f]}\n",
            ref[0], cur[0], ref[1], cur[1], ref[2], cur[2]);
    }

    static int format_raw(char *buf, int size, int led,
                          const int32_t *ch0, const int32_t *ch1, int count) {
        int pos = snprintf(buf, size, "{\"ev\":\"raw\",\"led\":%d,\"presamples\":0,\"ch0\":[", led);
        for (int i = 0; i < count && pos < size - 20; i++) {
            pos += snprintf(buf + pos, size - pos, "%ld%c",
                            (long)ch0[i], (i < count - 1) ? ',' : ']');
        }
        pos += snprintf(buf + pos, size - pos, ",\"ch1\":[");
        for (int i = 0; i < count && pos < size - 20; i++) {
            pos += snprintf(buf + pos, size - pos, "%ld%c",
                            (long)ch1[i], (i < count - 1) ? ',' : ']');
        }
        pos += snprintf(buf + pos, size - pos, "}\n");
        return pos;
    }

    static int format_data_raw(char *buf, int size, int led,
                               const int32_t *ch0, const int32_t *ch1,
                               int presamples, int total) {
        int pos = snprintf(buf, size,
            "{\"ev\":\"data_raw\",\"led\":%d,\"presamples\":%d,\"ch0\":[",
            led, presamples);
        for (int i = 0; i < total && pos < size - 20; i++) {
            pos += snprintf(buf + pos, size - pos, "%ld%c",
                            (long)ch0[i], (i < total - 1) ? ',' : ']');
        }
        pos += snprintf(buf + pos, size - pos, ",\"ch1\":[");
        for (int i = 0; i < total && pos < size - 20; i++) {
            pos += snprintf(buf + pos, size - pos, "%ld%c",
                            (long)ch1[i], (i < total - 1) ? ',' : ']');
        }
        pos += snprintf(buf + pos, size - pos, "}\n");
        return pos;
    }

    static int format_status(char *buf, int size, const char *state) {
        return snprintf(buf, size, "{\"ev\":\"status\",\"state\":\"%s\"}\n", state);
    }

    static int format_config(char *buf, int size, const Config &cfg) {
        return snprintf(buf, size,
            "{\"ev\":\"config\",\"osr\":%d,\"presamples\":%d,\"samples\":%d,"
            "\"pulse_ms\":%d,\"channels\":%d,\"deadtime\":%d,"
            "\"brightness_r\":%d,\"brightness_b\":%d,\"brightness_g\":%d,"
            "\"send_raw\":%d}\n",
            cfg.osr, cfg.presamples, cfg.samples,
            cfg.pulse_ms, cfg.channels, cfg.deadtime,
            cfg.brightness[0], cfg.brightness[1], cfg.brightness[2],
            cfg.send_raw);
    }

    static int format_error(char *buf, int size, const char *msg) {
        return snprintf(buf, size, "{\"ev\":\"error\",\"msg\":\"%s\"}\n", msg);
    }

    static int format_monitor(char *buf, int size,
                              const int32_t *ch0, const int32_t *ch1, int count) {
        int pos = snprintf(buf, size, "{\"ev\":\"monitor\",\"ch0\":[");
        for (int i = 0; i < count && pos < size - 20; i++) {
            pos += snprintf(buf + pos, size - pos, "%ld%c",
                            (long)ch0[i], (i < count - 1) ? ',' : ']');
        }
        pos += snprintf(buf + pos, size - pos, ",\"ch1\":[");
        for (int i = 0; i < count && pos < size - 20; i++) {
            pos += snprintf(buf + pos, size - pos, "%ld%c",
                            (long)ch1[i], (i < count - 1) ? ',' : ']');
        }
        pos += snprintf(buf + pos, size - pos, "}\n");
        return pos;
    }

private:
    static const char *_find(const char *json, const char *key) {
        int klen = strlen(key);
        while (*json) {
            if (*json != '"') { json++; continue; }
            json++;
            if (strncmp(json, key, klen) == 0 && json[klen] == '"') {
                json += klen + 1;
                while (*json && *json != ':') json++;
                if (*json == ':') {
                    json++;
                    while (*json == ' ' || *json == '\t' || *json == '\n' || *json == '\r')
                        json++;
                    return json;
                }
            }
            while (*json && *json != '"') {
                if (*json == '\\') json++;
                json++;
            }
            if (*json == '"') json++;
        }
        return nullptr;
    }

    static bool _scan_str(const char *json, const char *key, char *out, int max) {
        const char *v = _find(json, key);
        if (!v || *v != '"') return false;
        v++;
        int i = 0;
        while (*v && *v != '"' && i < max - 1) {
            if (*v == '\\') { v++; if (!*v) break; }
            out[i++] = *v++;
        }
        out[i] = '\0';
        return true;
    }

    static bool _scan_int(const char *json, const char *key, int *out) {
        const char *v = _find(json, key);
        if (!v) return false;
        bool neg = false;
        if (*v == '-') { neg = true; v++; }
        if (*v < '0' || *v > '9') return false;
        *out = 0;
        while (*v >= '0' && *v <= '9') {
            *out = *out * 10 + (*v - '0');
            v++;
        }
        if (neg) *out = -*out;
        return true;
    }
};
