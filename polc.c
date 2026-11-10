/*
 * TopoNet Prototype.pol Compiler (polc) - Native C Implementation
 * Translates Prototype.pol (.pol / .polh / .pollib) files into standard JSON topology definitions.
 *
 * Compilation:
 *     gcc -O2 -std=c99 polc.c -o polc.exe -lm
 *
 * Usage:
 *     polc <input.pol> [-o <output.json>] [-t <type>]
 *     polc --all
 */

#define _USE_MATH_DEFINES
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <math.h>
#include <stdbool.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#ifdef _WIN32
#include <io.h>
#include <direct.h>
#define PATH_SEP '\\'
#else
#include <unistd.h>
#include <sys/stat.h>
#define PATH_SEP '/'
#endif

static int str_case_cmp(const char *s1, const char *s2) {
    if (!s1 || !s2) return s1 ? 1 : (s2 ? -1 : 0);
    while (*s1 && *s2) {
        int diff = tolower((unsigned char)*s1) - tolower((unsigned char)*s2);
        if (diff != 0) return diff;
        s1++;
        s2++;
    }
    return tolower((unsigned char)*s1) - tolower((unsigned char)*s2);
}

#define MAX_NODES 128
#define MAX_LINKS 256
#define MAX_PATHS 32
#define MAX_HOPS 32
#define MAX_FILES 64
#define MAX_STR 128
#define MAX_TOKENS 8192

/* -------------------------------------------------------------------------- */
/* Dynamic String Buffer                                                      */
/* -------------------------------------------------------------------------- */
typedef struct {
    char *data;
    size_t len;
    size_t cap;
} StrBuf;

static void sb_init(StrBuf *sb) {
    sb->cap = 1024;
    sb->len = 0;
    sb->data = (char *)malloc(sb->cap);
    sb->data[0] = '\0';
}

static void sb_append(StrBuf *sb, const char *str) {
    if (!str) return;
    size_t slen = strlen(str);
    while (sb->len + slen + 1 > sb->cap) {
        sb->cap *= 2;
        sb->data = (char *)realloc(sb->data, sb->cap);
    }
    memcpy(sb->data + sb->len, str, slen);
    sb->len += slen;
    sb->data[sb->len] = '\0';
}

static void sb_append_char(StrBuf *sb, char c) {
    char s[2] = {c, '\0'};
    sb_append(sb, s);
}

static void sb_free(StrBuf *sb) {
    if (sb->data) {
        free(sb->data);
        sb->data = NULL;
    }
    sb->len = sb->cap = 0;
}

/* -------------------------------------------------------------------------- */
/* Data Structures                                                            */
/* -------------------------------------------------------------------------- */
typedef struct {
    char alias[MAX_STR];
    char type_name[MAX_STR];
    int count; // -1 for var/unlimited
} SpawnItem;

typedef struct {
    char src[MAX_STR];
    char cable[MAX_STR];
    char dst[MAX_STR];
} ConnItem;

typedef struct {
    char symbol[MAX_STR];
    char target_type[MAX_STR];
    bool is_unique;
    bool is_common;
} DefineItem;

typedef struct {
    char id[MAX_STR];
    char alias[MAX_STR];
    char name[MAX_STR];
    bool is_switch;
    int dpid;
    char role[MAX_STR];
    char subtext[MAX_STR];
    char ip[MAX_STR];
    char color[MAX_STR];
    char connected_to[MAX_STR];
    double x;
    double y;
} TopoNode;

typedef struct {
    char id[MAX_STR];
    char src[MAX_STR];
    char dst[MAX_STR];
    char label[MAX_STR];
    double bw_mbps;
    double delay_ms;
    int max_queue;
    char type[MAX_STR];
    char cable_alias[MAX_STR];
    char pen_color[MAX_STR];
    char path_segment[MAX_STR];
    bool is_bottleneck;
} TopoLink;

typedef struct {
    char id[MAX_STR];
    char name[MAX_STR];
    char role[MAX_STR];
    char hops[MAX_HOPS][MAX_STR];
    int hop_count;
    double delay_ms;
    double capacity_mbps;
    int queue_limit;
    int s1_output_port;
} TopoPath;

typedef struct {
    char topo_name[MAX_STR];
    char topo_type[MAX_STR];
    TopoNode nodes[MAX_NODES];
    int node_count;
    TopoLink links[MAX_LINKS];
    int link_count;
    TopoPath paths[MAX_PATHS];
    int path_count;
} Topology;

/* -------------------------------------------------------------------------- */
/* Utility Helpers                                                            */
/* -------------------------------------------------------------------------- */
static char *trim(char *str) {
    if (!str) return NULL;
    while (isspace((unsigned char)*str)) str++;
    if (*str == 0) return str;
    char *end = str + strlen(str) - 1;
    while (end > str && isspace((unsigned char)*end)) end--;
    end[1] = '\0';
    return str;
}

static bool file_exists(const char *path) {
    FILE *f = fopen(path, "r");
    if (f) {
        fclose(f);
        return true;
    }
    return false;
}

static void get_dir(const char *filepath, char *dir) {
    strcpy(dir, filepath);
    char *last = strrchr(dir, '/');
    char *last_b = strrchr(dir, '\\');
    if (last_b && (!last || last_b > last)) last = last_b;
    if (last) {
        *last = '\0';
    } else {
        strcpy(dir, ".");
    }
}

static void get_basename(const char *filepath, char *base) {
    const char *last = strrchr(filepath, '/');
    const char *last_b = strrchr(filepath, '\\');
    if (last_b && (!last || last_b > last)) last = last_b;
    const char *start = last ? last + 1 : filepath;
    strcpy(base, start);
    char *dot = strrchr(base, '.');
    if (dot) *dot = '\0';
}

static void make_parent_dir(const char *filepath) {
    char dir[512];
    get_dir(filepath, dir);
    if (strcmp(dir, ".") != 0 && strcmp(dir, "") != 0) {
#ifdef _WIN32
        _mkdir(dir);
#else
        mkdir(dir, 0755);
#endif
    }
}

/* -------------------------------------------------------------------------- */
/* Preprocessor: Resolving pull/include & Strip Comments                      */
/* -------------------------------------------------------------------------- */
static const char *SEARCH_PATHS[] = {
    ".",
    "lib",
    "pol_src",
    "pol_src/lib"
};
static const int NUM_SEARCH_PATHS = 4;

static bool resolve_include_path(const char *target, const char *cur_dir, char *out_path) {
    char clean[MAX_STR];
    strncpy(clean, target, MAX_STR - 1);
    clean[MAX_STR - 1] = '\0';
    trim(clean);

    // Strip quotes or angle brackets
    size_t clen = strlen(clean);
    if (clen >= 2 && ((clean[0] == '"' && clean[clen - 1] == '"') ||
                     (clean[0] == '<' && clean[clen - 1] == '>'))) {
        clean[clen - 1] = '\0';
        memmove(clean, clean + 1, clen);
    }

    if (strcmp(clean, "std") == 0 || strcmp(clean, "lib.std") == 0 || strcmp(clean, "header files") == 0) {
        strcpy(clean, "std.polh");
    } else if (strncmp(clean, "lib.", 4) == 0) {
        char temp[MAX_STR];
        snprintf(temp, sizeof(temp), "%s.pollib", clean + 4);
        strcpy(clean, temp);
    }

    // 1. Direct path relative to current file's directory
    char cand[512];
    snprintf(cand, sizeof(cand), "%s/%s", cur_dir, clean);
    if (file_exists(cand)) {
        strcpy(out_path, cand);
        return true;
    }

    // 2. Check extensions (.polh, .pollib, .pol)
    const char *exts[] = {".polh", ".pollib", ".pol"};
    for (int e = 0; e < 3; e++) {
        snprintf(cand, sizeof(cand), "%s/%s%s", cur_dir, clean, exts[e]);
        if (file_exists(cand)) {
            strcpy(out_path, cand);
            return true;
        }
    }

    // 3. Check search paths
    for (int p = 0; p < NUM_SEARCH_PATHS; p++) {
        snprintf(cand, sizeof(cand), "%s/%s", SEARCH_PATHS[p], clean);
        if (file_exists(cand)) {
            strcpy(out_path, cand);
            return true;
        }
        for (int e = 0; e < 3; e++) {
            snprintf(cand, sizeof(cand), "%s/%s%s", SEARCH_PATHS[p], clean, exts[e]);
            if (file_exists(cand)) {
                strcpy(out_path, cand);
                return true;
            }
        }
    }

    return false;
}

static bool preprocess_file(const char *filepath, StrBuf *out_buf, char visited[MAX_FILES][MAX_STR], int *visited_count) {
    if (*visited_count >= MAX_FILES) return false;

    // Check circular include
    for (int i = 0; i < *visited_count; i++) {
        if (strcmp(visited[i], filepath) == 0) {
            return true; // Already processed
        }
    }
    strcpy(visited[(*visited_count)++], filepath);

    FILE *f = fopen(filepath, "r");
    if (!f) return false;

    char cur_dir[512];
    get_dir(filepath, cur_dir);

    char line[1024];
    bool in_block_comment = false;

    while (fgets(line, sizeof(line), f)) {
        char *p = line;

        // Multi-line comment state handling
        if (in_block_comment) {
            char *end_c = strstr(p, "*/");
            if (end_c) {
                in_block_comment = false;
                p = end_c + 2;
            } else {
                continue;
            }
        }

        // Look for start of block comment /*
        char *start_c = strstr(p, "/*");
        if (start_c) {
            char *end_c = strstr(start_c + 2, "*/");
            if (end_c) {
                // remove comment from line
                memmove(start_c, end_c + 2, strlen(end_c + 2) + 1);
            } else {
                *start_c = '\0';
                in_block_comment = true;
            }
        }

        // Strip single line comments: # or //
        char *c1 = strchr(p, '#');
        char *c2 = strstr(p, "//");
        if (c1 && c2) {
            if (c1 < c2) *c1 = '\0';
            else *c2 = '\0';
        } else if (c1) {
            *c1 = '\0';
        } else if (c2) {
            *c2 = '\0';
        }

        char *t = trim(p);
        if (*t == '\0') continue;

        // Check for pull or include
        if (strncmp(t, "pull", 4) == 0 || strncmp(t, "include", 7) == 0) {
            char *arg = NULL;
            if (strncmp(t, "pull", 4) == 0) {
                arg = t + 4;
                while (*arg == '@' || *arg == ':' || isspace((unsigned char)*arg)) arg++;
            } else {
                arg = t + 7;
                while (isspace((unsigned char)*arg)) arg++;
            }

            char inc_target[MAX_STR] = {0};
            char *semi = strchr(arg, ';');
            if (semi) *semi = '\0';
            strncpy(inc_target, trim(arg), MAX_STR - 1);

            char resolved[512];
            if (resolve_include_path(inc_target, cur_dir, resolved)) {
                preprocess_file(resolved, out_buf, visited, visited_count);
                continue;
            }
        }

        sb_append(out_buf, t);
        sb_append_char(out_buf, '\n');
    }

    fclose(f);
    return true;
}

/* -------------------------------------------------------------------------- */
/* Lexer / Tokenizer                                                          */
/* -------------------------------------------------------------------------- */
typedef enum {
    TOK_EOF,
    TOK_IDENT,
    TOK_STRING,
    TOK_NUMBER,
    TOK_LBRACE,
    TOK_RBRACE,
    TOK_LPAREN,
    TOK_RPAREN,
    TOK_COLON,
    TOK_SEMICOLON,
    TOK_COMMA,
    TOK_EQUALS,
    TOK_KW_TOPOLOGY,
    TOK_KW_SPAWNS,
    TOK_KW_CONNECTIONS,
    TOK_KW_SPAWN,
    TOK_KW_ALIAS,
    TOK_KW_AS,
    TOK_KW_DETAIL,
    TOK_KW_DEFINE,
    TOK_KW_DEFINE_MULTI,
    TOK_MODIFIER
} TokenType;

typedef struct {
    TokenType type;
    char text[MAX_STR];
} Token;

static void tokenize(const char *src, Token *tokens, int *num_tokens) {
    *num_tokens = 0;
    const char *p = src;

    while (*p && *num_tokens < MAX_TOKENS - 1) {
        if (isspace((unsigned char)*p)) {
            p++;
            continue;
        }

        Token *tok = &tokens[*num_tokens];
        tok->text[0] = '\0';

        if (*p == '{') {
            tok->type = TOK_LBRACE;
            strcpy(tok->text, "{");
            (*num_tokens)++;
            p++;
            continue;
        }
        if (*p == '}') {
            tok->type = TOK_RBRACE;
            strcpy(tok->text, "}");
            (*num_tokens)++;
            p++;
            continue;
        }
        if (*p == '(') {
            tok->type = TOK_LPAREN;
            strcpy(tok->text, "(");
            (*num_tokens)++;
            p++;
            continue;
        }
        if (*p == ')') {
            tok->type = TOK_RPAREN;
            strcpy(tok->text, ")");
            (*num_tokens)++;
            p++;
            continue;
        }
        if (*p == ':') {
            if (*(p + 1) == ':') {
                p += 2;
                continue;
            }
            tok->type = TOK_COLON;
            strcpy(tok->text, ":");
            (*num_tokens)++;
            p++;
            continue;
        }
        if (*p == ';') {
            tok->type = TOK_SEMICOLON;
            strcpy(tok->text, ";");
            (*num_tokens)++;
            p++;
            continue;
        }
        if (*p == ',') {
            tok->type = TOK_COMMA;
            strcpy(tok->text, ",");
            (*num_tokens)++;
            p++;
            continue;
        }
        if (*p == '=') {
            tok->type = TOK_EQUALS;
            strcpy(tok->text, "=");
            (*num_tokens)++;
            p++;
            continue;
        }

        // Modifiers: --unique, --common
        if (*p == '-' && *(p + 1) == '-') {
            p += 2;
            int len = 0;
            while (isalnum((unsigned char)*p) || *p == '_') {
                if (len < MAX_STR - 1) tok->text[len++] = *p;
                p++;
            }
            tok->text[len] = '\0';
            tok->type = TOK_MODIFIER;
            (*num_tokens)++;
            continue;
        }

        // Quoted strings
        if (*p == '"' || *p == '\'') {
            char quote = *p++;
            int len = 0;
            while (*p && *p != quote) {
                if (*p == '\\' && *(p + 1)) p++;
                if (len < MAX_STR - 1) tok->text[len++] = *p;
                p++;
            }
            if (*p == quote) p++;
            tok->text[len] = '\0';
            tok->type = TOK_STRING;
            (*num_tokens)++;
            continue;
        }

        // Directives: __SPAWNS__, __CONNECTIONS__
        if (*p == '_' && *(p + 1) == '_') {
            int len = 0;
            while (isalnum((unsigned char)*p) || *p == '_') {
                if (len < MAX_STR - 1) tok->text[len++] = *p;
                p++;
            }
            tok->text[len] = '\0';
            if (strcmp(tok->text, "__SPAWNS__") == 0) {
                tok->type = TOK_KW_SPAWNS;
            } else if (strcmp(tok->text, "__CONNECTIONS__") == 0) {
                tok->type = TOK_KW_CONNECTIONS;
            } else {
                tok->type = TOK_IDENT;
            }
            (*num_tokens)++;
            continue;
        }

        // Identifiers and numbers
        if (isalnum((unsigned char)*p) || *p == '_' || *p == '&' || *p == '@' || *p == '.') {
            int len = 0;
            while (isalnum((unsigned char)*p) || *p == '_' || *p == '&' || *p == '@' || *p == '.') {
                if (len < MAX_STR - 1) tok->text[len++] = *p;
                p++;
            }
            tok->text[len] = '\0';

            if (strcmp(tok->text, "topology") == 0) tok->type = TOK_KW_TOPOLOGY;
            else if (strcmp(tok->text, "spawns") == 0) tok->type = TOK_KW_SPAWNS;
            else if (strcmp(tok->text, "connections") == 0) tok->type = TOK_KW_CONNECTIONS;
            else if (strcmp(tok->text, "spawn") == 0) tok->type = TOK_KW_SPAWN;
            else if (strcmp(tok->text, "alias") == 0) tok->type = TOK_KW_ALIAS;
            else if (strcmp(tok->text, "as") == 0) tok->type = TOK_KW_AS;
            else if (strcmp(tok->text, "detail") == 0) tok->type = TOK_KW_DETAIL;
            else if (strcmp(tok->text, "define") == 0) tok->type = TOK_KW_DEFINE;
            else if (strcmp(tok->text, "define_multi") == 0) tok->type = TOK_KW_DEFINE_MULTI;
            else if (isdigit((unsigned char)tok->text[0])) tok->type = TOK_NUMBER;
            else tok->type = TOK_IDENT;

            (*num_tokens)++;
            continue;
        }

        p++; // Skip unrecognized char
    }

    tokens[*num_tokens].type = TOK_EOF;
    tokens[*num_tokens].text[0] = '\0';
}

/* -------------------------------------------------------------------------- */
/* Parser & Intermediate Representation Builder                               */
/* -------------------------------------------------------------------------- */
typedef struct {
    SpawnItem spawns[MAX_NODES];
    int spawn_count;
    ConnItem conns[MAX_LINKS];
    int conn_count;
    DefineItem defines[MAX_NODES];
    int define_count;
    char topology_name[MAX_STR];
} ParseResult;

static void parse_tokens(Token *tokens, int num_tokens, ParseResult *res) {
    res->spawn_count = 0;
    res->conn_count = 0;
    res->define_count = 0;
    res->topology_name[0] = '\0';

    int i = 0;
    while (i < num_tokens && tokens[i].type != TOK_EOF) {
        // topology <Name>:
        if (tokens[i].type == TOK_KW_TOPOLOGY) {
            i++;
            if (tokens[i].type == TOK_IDENT) {
                strncpy(res->topology_name, tokens[i].text, MAX_STR - 1);
                i++;
            }
            if (tokens[i].type == TOK_COLON) i++;
            continue;
        }

        // spawns { ... } or __SPAWNS__ { ... }
        if (tokens[i].type == TOK_KW_SPAWNS) {
            i++;
            if (tokens[i].type == TOK_LBRACE) i++;
            while (i < num_tokens && tokens[i].type != TOK_RBRACE && tokens[i].type != TOK_EOF) {
                if (tokens[i].type == TOK_KW_SPAWN) {
                    i++;
                    char type_name[MAX_STR] = {0};
                    if (tokens[i].type == TOK_IDENT) {
                        strncpy(type_name, tokens[i].text, MAX_STR - 1);
                        i++;
                    }
                    int count = -1;
                    if (tokens[i].type == TOK_NUMBER) {
                        count = atoi(tokens[i].text);
                        i++;
                    }
                    if (tokens[i].type == TOK_KW_ALIAS || tokens[i].type == TOK_KW_AS) {
                        i++;
                    }
                    // Comma separated aliases
                    while (i < num_tokens && tokens[i].type == TOK_IDENT) {
                        if (res->spawn_count < MAX_NODES) {
                            SpawnItem *sp = &res->spawns[res->spawn_count++];
                            strncpy(sp->alias, tokens[i].text, MAX_STR - 1);
                            strncpy(sp->type_name, type_name, MAX_STR - 1);
                            sp->count = count;
                        }
                        i++;
                        if (tokens[i].type == TOK_COMMA) {
                            i++;
                        } else {
                            break;
                        }
                    }
                    if (tokens[i].type == TOK_SEMICOLON) i++;
                } else {
                    i++;
                }
            }
            if (tokens[i].type == TOK_RBRACE) i++;
            continue;
        }

        // connections { ... } or __CONNECTIONS__ { ... }
        if (tokens[i].type == TOK_KW_CONNECTIONS) {
            i++;
            if (tokens[i].type == TOK_LBRACE) i++;
            while (i < num_tokens && tokens[i].type != TOK_RBRACE && tokens[i].type != TOK_EOF) {
                if (tokens[i].type == TOK_LPAREN) {
                    i++; // consume '('
                    char src[MAX_STR] = {0}, cable[MAX_STR] = {0}, dst[MAX_STR] = {0};
                    if (tokens[i].type == TOK_IDENT) { strncpy(src, tokens[i].text, MAX_STR - 1); i++; }
                    if (tokens[i].type == TOK_COMMA) i++;
                    if (tokens[i].type == TOK_IDENT) { strncpy(cable, tokens[i].text, MAX_STR - 1); i++; }
                    if (tokens[i].type == TOK_COMMA) i++;
                    if (tokens[i].type == TOK_IDENT) { strncpy(dst, tokens[i].text, MAX_STR - 1); i++; }
                    if (tokens[i].type == TOK_RPAREN) i++;
                    if (tokens[i].type == TOK_SEMICOLON) i++;

                    if (src[0] && dst[0] && res->conn_count < MAX_LINKS) {
                        ConnItem *c = &res->conns[res->conn_count++];
                        strncpy(c->src, src, MAX_STR - 1);
                        strncpy(c->cable, cable[0] ? cable : "hi", MAX_STR - 1);
                        strncpy(c->dst, dst, MAX_STR - 1);
                    }
                } else {
                    i++;
                }
            }
            if (tokens[i].type == TOK_RBRACE) i++;
            continue;
        }

        i++;
    }
}

/* -------------------------------------------------------------------------- */
/* Spring Embedder / Layout Engine in C                                       */
/* -------------------------------------------------------------------------- */
static void compute_spring_layout(Topology *topo) {
    int n = topo->node_count;
    if (n == 0) return;

    // Initial positioning in circle
    double pos_x[MAX_NODES], pos_y[MAX_NODES];
    for (int i = 0; i < n; i++) {
        double angle = 2.0 * M_PI * i / n;
        pos_x[i] = 0.50 + 0.30 * cos(angle);
        pos_y[i] = 0.50 + 0.30 * sin(angle);
    }

    double k = sqrt(1.0 / (double)n);
    double temp = 0.15;
    int iterations = 60;

    for (int iter = 0; iter < iterations; iter++) {
        double disp_x[MAX_NODES] = {0}, disp_y[MAX_NODES] = {0};

        // Repulsive forces between all pairs
        for (int v = 0; v < n; v++) {
            for (int u = v + 1; u < n; u++) {
                double dx = pos_x[v] - pos_x[u];
                double dy = pos_y[v] - pos_y[u];
                double dist = sqrt(dx * dx + dy * dy);
                if (dist < 1e-4) dist = 1e-4;
                double force = (k * k) / dist;
                disp_x[v] += (dx / dist) * force;
                disp_y[v] += (dy / dist) * force;
                disp_x[u] -= (dx / dist) * force;
                disp_y[u] -= (dy / dist) * force;
            }
        }

        // Attractive forces along links
        for (int e = 0; e < topo->link_count; e++) {
            int v = -1, u = -1;
            for (int i = 0; i < n; i++) {
                if (strcmp(topo->nodes[i].id, topo->links[e].src) == 0) v = i;
                if (strcmp(topo->nodes[i].id, topo->links[e].dst) == 0) u = i;
            }
            if (v >= 0 && u >= 0 && v != u) {
                double dx = pos_x[v] - pos_x[u];
                double dy = pos_y[v] - pos_y[u];
                double dist = sqrt(dx * dx + dy * dy);
                if (dist < 1e-4) dist = 1e-4;
                double force = (dist * dist) / k;
                disp_x[v] -= (dx / dist) * force;
                disp_y[v] -= (dy / dist) * force;
                disp_x[u] += (dx / dist) * force;
                disp_y[u] += (dy / dist) * force;
            }
        }

        // Update positions with temperature cap
        for (int i = 0; i < n; i++) {
            double dlen = sqrt(disp_x[i] * disp_x[i] + disp_y[i] * disp_y[i]);
            if (dlen > 1e-4) {
                double step = dlen < temp ? dlen : temp;
                pos_x[i] += (disp_x[i] / dlen) * step;
                pos_y[i] += (disp_y[i] / dlen) * step;
            }
        }

        temp *= 0.95;
    }

    // Normalize to [0.10, 0.90]
    double min_x = pos_x[0], max_x = pos_x[0];
    double min_y = pos_y[0], max_y = pos_y[0];
    for (int i = 1; i < n; i++) {
        if (pos_x[i] < min_x) min_x = pos_x[i];
        if (pos_x[i] > max_x) max_x = pos_x[i];
        if (pos_y[i] < min_y) min_y = pos_y[i];
        if (pos_y[i] > max_y) max_y = pos_y[i];
    }

    double span_x = (max_x - min_x > 1e-4) ? (max_x - min_x) : 1.0;
    double span_y = (max_y - min_y > 1e-4) ? (max_y - min_y) : 1.0;

    for (int i = 0; i < n; i++) {
        double nx = 0.10 + 0.80 * ((pos_x[i] - min_x) / span_x);
        double ny = 0.15 + 0.70 * ((pos_y[i] - min_y) / span_y);
        topo->nodes[i].x = round(nx * 100.0) / 100.0;
        topo->nodes[i].y = round(ny * 100.0) / 100.0;
    }
}

static void apply_coordinates(Topology *topo, const char *layout_type) {
    int sw_count = 0, h_count = 0;
    for (int i = 0; i < topo->node_count; i++) {
        if (topo->nodes[i].is_switch) sw_count++;
        else h_count++;
    }

    // 1. Diamond Topology
    if (str_case_cmp(layout_type, "diamond") == 0 || (sw_count == 4 && h_count == 4 && strstr(topo->topo_name, "Diamond"))) {
        for (int i = 0; i < topo->node_count; i++) {
            TopoNode *nd = &topo->nodes[i];
            if (strcmp(nd->id, "s1") == 0) { nd->x = 0.26; nd->y = 0.50; }
            else if (strcmp(nd->id, "s2") == 0) { nd->x = 0.50; nd->y = 0.22; }
            else if (strcmp(nd->id, "s3") == 0) { nd->x = 0.50; nd->y = 0.78; }
            else if (strcmp(nd->id, "s4") == 0) { nd->x = 0.74; nd->y = 0.50; }
            else if (strcmp(nd->id, "h1") == 0) { nd->x = 0.08; nd->y = 0.28; }
            else if (strcmp(nd->id, "h3") == 0) { nd->x = 0.08; nd->y = 0.72; }
            else if (strcmp(nd->id, "h2") == 0) { nd->x = 0.92; nd->y = 0.28; }
            else if (strcmp(nd->id, "h4") == 0) { nd->x = 0.92; nd->y = 0.72; }
        }
        return;
    }

    // 2. Star Topology
    if (str_case_cmp(layout_type, "star") == 0 || (sw_count == 1 && h_count >= 1)) {
        for (int i = 0; i < topo->node_count; i++) {
            if (topo->nodes[i].is_switch) {
                topo->nodes[i].x = 0.50;
                topo->nodes[i].y = 0.50;
            }
        }
        int h_idx = 0;
        for (int i = 0; i < topo->node_count; i++) {
            if (!topo->nodes[i].is_switch) {
                double angle = (2.0 * M_PI * h_idx) / (h_count ? h_count : 1) - (M_PI / 2.0);
                topo->nodes[i].x = round((0.50 + 0.33 * cos(angle)) * 100.0) / 100.0;
                topo->nodes[i].y = round((0.50 + 0.33 * sin(angle)) * 100.0) / 100.0;
                h_idx++;
            }
        }
        return;
    }

    // 3. Bus Topology
    if (str_case_cmp(layout_type, "bus") == 0) {
        int s_idx = 0;
        double step = sw_count > 1 ? (0.62 / (sw_count - 1)) : 0.5;
        for (int i = 0; i < topo->node_count; i++) {
            if (topo->nodes[i].is_switch) {
                topo->nodes[i].x = round((0.19 + s_idx * step) * 100.0) / 100.0;
                topo->nodes[i].y = 0.50;
                s_idx++;
            }
        }
        int h_idx = 0;
        for (int i = 0; i < topo->node_count; i++) {
            if (!topo->nodes[i].is_switch) {
                // Find parent switch x
                double px = 0.50;
                for (int j = 0; j < topo->node_count; j++) {
                    if (strcmp(topo->nodes[j].id, topo->nodes[i].connected_to) == 0) {
                        px = topo->nodes[j].x;
                        break;
                    }
                }
                topo->nodes[i].x = px;
                topo->nodes[i].y = (h_idx % 2 == 0) ? 0.22 : 0.78;
                h_idx++;
            }
        }
        return;
    }

    // 4. Ring Topology
    if (str_case_cmp(layout_type, "ring") == 0) {
        int s_idx = 0;
        for (int i = 0; i < topo->node_count; i++) {
            if (topo->nodes[i].is_switch) {
                double angle = (2.0 * M_PI * s_idx) / (sw_count ? sw_count : 1) - (3.0 * M_PI / 4.0);
                topo->nodes[i].x = round((0.50 + 0.22 * cos(angle) * 1.3) * 100.0) / 100.0;
                topo->nodes[i].y = round((0.50 + 0.18 * sin(angle) * 1.3) * 100.0) / 100.0;
                s_idx++;
            }
        }
        for (int i = 0; i < topo->node_count; i++) {
            if (!topo->nodes[i].is_switch) {
                double px = 0.50, py = 0.50;
                for (int j = 0; j < topo->node_count; j++) {
                    if (strcmp(topo->nodes[j].id, topo->nodes[i].connected_to) == 0) {
                        px = topo->nodes[j].x;
                        py = topo->nodes[j].y;
                        break;
                    }
                }
                double vx = px - 0.50;
                double vy = py - 0.50;
                double mag = sqrt(vx * vx + vy * vy);
                if (mag < 1e-4) mag = 1.0;
                topo->nodes[i].x = round((0.50 + (vx / mag) * 0.44) * 100.0) / 100.0;
                topo->nodes[i].y = round((0.50 + (vy / mag) * 0.38) * 100.0) / 100.0;
            }
        }
        return;
    }

    // 5. Mesh Topology
    if (str_case_cmp(layout_type, "mesh") == 0) {
        for (int i = 0; i < topo->node_count; i++) {
            TopoNode *nd = &topo->nodes[i];
            if (strcmp(nd->id, "s1") == 0) { nd->x = 0.35; nd->y = 0.32; }
            else if (strcmp(nd->id, "s2") == 0) { nd->x = 0.65; nd->y = 0.32; }
            else if (strcmp(nd->id, "s3") == 0) { nd->x = 0.35; nd->y = 0.68; }
            else if (strcmp(nd->id, "s4") == 0) { nd->x = 0.65; nd->y = 0.68; }
            else if (strcmp(nd->id, "h1") == 0) { nd->x = 0.10; nd->y = 0.28; }
            else if (strcmp(nd->id, "h3") == 0) { nd->x = 0.10; nd->y = 0.72; }
            else if (strcmp(nd->id, "h2") == 0) { nd->x = 0.90; nd->y = 0.28; }
            else if (strcmp(nd->id, "h4") == 0) { nd->x = 0.90; nd->y = 0.72; }
        }
        return;
    }

    // Fallback: Spring embedder layout for arbitrary topology
    compute_spring_layout(topo);
}

/* -------------------------------------------------------------------------- */
/* Synthesis & Topology Graph Construction                                    */
/* -------------------------------------------------------------------------- */
static int find_or_add_node(Topology *topo, const char *alias, ParseResult *res, bool is_src) {
    for (int i = 0; i < topo->node_count; i++) {
        if (strcmp(topo->nodes[i].alias, alias) == 0) return i;
    }

    if (topo->node_count >= MAX_NODES) return 0;

    TopoNode *nd = &topo->nodes[topo->node_count++];
    memset(nd, 0, sizeof(TopoNode));
    strncpy(nd->alias, alias, MAX_STR - 1);

    // Find spawn type if any
    char spawn_type[MAX_STR] = {0};
    for (int s = 0; s < res->spawn_count; s++) {
        if (strcmp(res->spawns[s].alias, alias) == 0) {
            strncpy(spawn_type, res->spawns[s].type_name, MAX_STR - 1);
            break;
        }
    }

    // Determine if host or switch
    char base[MAX_STR];
    strncpy(base, spawn_type[0] ? spawn_type : alias, MAX_STR - 1);
    for (char *p = base; *p; p++) *p = tolower((unsigned char)*p);

    bool is_host = false;
    if (strstr(base, "sender") || strstr(base, "receiver") || strstr(base, "reciever") || strstr(base, "host")) {
        is_host = true;
    } else if (strstr(base, "ingress") || strstr(base, "egress") || strstr(base, "switch") || strstr(base, "hub")) {
        is_host = false;
    } else if (alias[0] == 'h' && isdigit((unsigned char)alias[1])) {
        is_host = true;
    } else if (alias[0] == 's' && isdigit((unsigned char)alias[1])) {
        is_host = false;
    } else {
        is_host = false; // default switch
    }

    nd->is_switch = !is_host;

    if (is_host) {
        int h_count = 0;
        for (int i = 0; i < topo->node_count - 1; i++) {
            if (!topo->nodes[i].is_switch) h_count++;
        }
        if (alias[0] == 'h' && isdigit((unsigned char)alias[1])) {
            strncpy(nd->id, alias, MAX_STR - 1);
        } else {
            snprintf(nd->id, sizeof(nd->id), "h%d", h_count + 1);
        }
        for (char *c = nd->id; *c; c++) *c = tolower((unsigned char)*c);
        snprintf(nd->name, sizeof(nd->name), "%s", nd->id);
        nd->name[0] = toupper((unsigned char)nd->name[0]);

        int hnum = 1;
        if (isdigit((unsigned char)nd->id[1])) hnum = atoi(nd->id + 1);
        snprintf(nd->ip, sizeof(nd->ip), "10.0.0.%d", hnum);

        if (hnum == 1) {
            strcpy(nd->role, "main_sender");
            strcpy(nd->color, "#1e66f5");
        } else if (hnum == 2) {
            strcpy(nd->role, "main_receiver");
            strcpy(nd->color, "#a6e3a1");
        } else if (hnum == 3) {
            strcpy(nd->role, "cross_sender");
            strcpy(nd->color, "#f38ba8");
        } else if (hnum == 4) {
            strcpy(nd->role, "cross_receiver");
            strcpy(nd->color, "#df8e1d");
        } else {
            strcpy(nd->role, "aux_host");
            strcpy(nd->color, "#a6adc8");
        }
        strncpy(nd->subtext, nd->ip, MAX_STR - 1);
    } else {
        int s_count = 0;
        for (int i = 0; i < topo->node_count - 1; i++) {
            if (topo->nodes[i].is_switch) s_count++;
        }
        if (alias[0] == 's' && isdigit((unsigned char)alias[1])) {
            strncpy(nd->id, alias, MAX_STR - 1);
        } else {
            snprintf(nd->id, sizeof(nd->id), "s%d", s_count + 1);
        }
        for (char *c = nd->id; *c; c++) *c = tolower((unsigned char)*c);
        snprintf(nd->name, sizeof(nd->name), "%s", nd->id);
        nd->name[0] = toupper((unsigned char)nd->name[0]);

        nd->dpid = isdigit((unsigned char)nd->id[1]) ? atoi(nd->id + 1) : (s_count + 1);

        char alow[MAX_STR];
        strncpy(alow, alias, MAX_STR - 1);
        for (char *c = alow; *c; c++) *c = tolower((unsigned char)*c);

        if (strstr(alow, "in") || strstr(base, "ingress") || strcmp(nd->id, "s1") == 0) {
            strcpy(nd->role, "ingress");
            strcpy(nd->subtext, "Ingress");
        } else if (strstr(alow, "out") || strstr(base, "egress")) {
            strcpy(nd->role, "egress");
            strcpy(nd->subtext, "Egress");
        } else {
            strcpy(nd->role, "core");
            strcpy(nd->subtext, "Core");
        }
    }

    return topo->node_count - 1;
}

static void synthesize_paths(Topology *topo) {
    // Find Ingress and Egress switches
    char ingress[MAX_STR] = {0};
    char egress[MAX_STR] = {0};

    int sw_indices[MAX_NODES];
    int sw_count = 0;
    for (int i = 0; i < topo->node_count; i++) {
        if (topo->nodes[i].is_switch) {
            sw_indices[sw_count++] = i;
            if (strcmp(topo->nodes[i].role, "ingress") == 0 && !ingress[0]) {
                strcpy(ingress, topo->nodes[i].id);
            }
            if (strcmp(topo->nodes[i].role, "egress") == 0) {
                strcpy(egress, topo->nodes[i].id);
            }
        }
    }

    if (!ingress[0] && sw_count > 0) strcpy(ingress, topo->nodes[sw_indices[0]].id);
    if (!egress[0] && sw_count > 0) strcpy(egress, topo->nodes[sw_indices[sw_count - 1]].id);

    if (sw_count <= 1) {
        // Direct single-switch path
        if (sw_count == 1) {
            TopoPath *p = &topo->paths[topo->path_count++];
            strcpy(p->id, "path_a");
            snprintf(p->name, sizeof(p->name), "Direct (%s)", topo->nodes[sw_indices[0]].name);
            strcpy(p->role, "primary");
            strcpy(p->hops[0], topo->nodes[sw_indices[0]].id);
            p->hop_count = 1;
            p->delay_ms = 1.0;
            p->capacity_mbps = 100.0;
            p->queue_limit = 1000;
            p->s1_output_port = 1;
        }
        return;
    }

    // Build switch adjacency matrix
    int adj[MAX_NODES][MAX_NODES] = {0};
    for (int e = 0; e < topo->link_count; e++) {
        int u = -1, v = -1;
        for (int i = 0; i < sw_count; i++) {
            if (strcmp(topo->nodes[sw_indices[i]].id, topo->links[e].src) == 0) u = i;
            if (strcmp(topo->nodes[sw_indices[i]].id, topo->links[e].dst) == 0) v = i;
        }
        if (u >= 0 && v >= 0 && u != v) {
            adj[u][v] = 1;
            adj[v][u] = 1;
        }
    }

    int start_sw = -1, end_sw = -1;
    for (int i = 0; i < sw_count; i++) {
        if (strcmp(topo->nodes[sw_indices[i]].id, ingress) == 0) start_sw = i;
        if (strcmp(topo->nodes[sw_indices[i]].id, egress) == 0) end_sw = i;
    }

    if (start_sw < 0 || end_sw < 0 || start_sw == end_sw) return;

    // BFS / DFS for up to 2 distinct paths
    int visited[MAX_NODES] = {0};
    int queue[MAX_NODES];
    int parent[MAX_NODES];
    for (int i = 0; i < MAX_NODES; i++) parent[i] = -1;

    int qhead = 0, qtail = 0;
    queue[qtail++] = start_sw;
    visited[start_sw] = 1;

    while (qhead < qtail) {
        int curr = queue[qhead++];
        if (curr == end_sw) break;
        for (int next = 0; next < sw_count; next++) {
            if (adj[curr][next] && !visited[next]) {
                visited[next] = 1;
                parent[next] = curr;
                queue[qtail++] = next;
            }
        }
    }

    if (visited[end_sw]) {
        // Trace Path A
        int trace[MAX_HOPS];
        int tlen = 0;
        int cur = end_sw;
        while (cur != -1 && tlen < MAX_HOPS) {
            trace[tlen++] = cur;
            cur = parent[cur];
        }

        TopoPath *pa = &topo->paths[topo->path_count++];
        strcpy(pa->id, "path_a");
        strcpy(pa->role, "primary");
        pa->hop_count = tlen;
        pa->delay_ms = 5.0;
        pa->capacity_mbps = 10.0;
        pa->queue_limit = 100;
        pa->s1_output_port = 2;

        char path_str[MAX_STR] = {0};
        for (int i = 0; i < tlen; i++) {
            int sw_i = trace[tlen - 1 - i];
            strcpy(pa->hops[i], topo->nodes[sw_indices[sw_i]].id);
            if (i > 0) strcat(path_str, " -> ");
            strcat(path_str, topo->nodes[sw_indices[sw_i]].name);

            // Mark intermediate switches as primary
            if (i > 0 && i < tlen - 1) {
                if (strcmp(topo->nodes[sw_indices[sw_i]].role, "ingress") != 0 &&
                    strcmp(topo->nodes[sw_indices[sw_i]].role, "egress") != 0) {
                    strcpy(topo->nodes[sw_indices[sw_i]].role, "primary");
                    strcpy(topo->nodes[sw_indices[sw_i]].subtext, "Primary");
                }
            }
        }
        snprintf(pa->name, sizeof(pa->name), "Path-A (%s)", path_str);

        // Mark links along path_a
        for (int i = 0; i < pa->hop_count - 1; i++) {
            const char *u = pa->hops[i];
            const char *v = pa->hops[i + 1];
            for (int e = 0; e < topo->link_count; e++) {
                TopoLink *lk = &topo->links[e];
                if ((strcmp(lk->src, u) == 0 && strcmp(lk->dst, v) == 0) ||
                    (strcmp(lk->src, v) == 0 && strcmp(lk->dst, u) == 0)) {
                    strcpy(lk->path_segment, "path_a");
                    lk->is_bottleneck = true;
                    if (strcmp(u, ingress) == 0) strcpy(lk->label, "Path A");
                    else strcpy(lk->label, "Path A (egress)");
                }
            }
        }

        // Try to find alternate Path B by removing one intermediate edge
        if (tlen > 2) {
            int rem_u = trace[tlen - 2];
            int rem_v = trace[tlen - 3];
            adj[rem_u][rem_v] = 0;
            adj[rem_v][rem_u] = 0;

            for (int i = 0; i < MAX_NODES; i++) { visited[i] = 0; parent[i] = -1; }
            qhead = qtail = 0;
            queue[qtail++] = start_sw;
            visited[start_sw] = 1;

            while (qhead < qtail) {
                int c = queue[qhead++];
                if (c == end_sw) break;
                for (int next = 0; next < sw_count; next++) {
                    if (adj[c][next] && !visited[next]) {
                        visited[next] = 1;
                        parent[next] = c;
                        queue[qtail++] = next;
                    }
                }
            }

            if (visited[end_sw]) {
                int btrace[MAX_HOPS];
                int blen = 0;
                int bcur = end_sw;
                while (bcur != -1 && blen < MAX_HOPS) {
                    btrace[blen++] = bcur;
                    bcur = parent[bcur];
                }

                TopoPath *pb = &topo->paths[topo->path_count++];
                strcpy(pb->id, "path_b");
                strcpy(pb->role, "alternate");
                pb->hop_count = blen;
                pb->delay_ms = 15.0;
                pb->capacity_mbps = 10.0;
                pb->queue_limit = 100;
                pb->s1_output_port = 3;

                char bpath_str[MAX_STR] = {0};
                for (int i = 0; i < blen; i++) {
                    int sw_i = btrace[blen - 1 - i];
                    strcpy(pb->hops[i], topo->nodes[sw_indices[sw_i]].id);
                    if (i > 0) strcat(bpath_str, " -> ");
                    strcat(bpath_str, topo->nodes[sw_indices[sw_i]].name);

                    if (i > 0 && i < blen - 1) {
                        if (strcmp(topo->nodes[sw_indices[sw_i]].role, "ingress") != 0 &&
                            strcmp(topo->nodes[sw_indices[sw_i]].role, "egress") != 0 &&
                            strcmp(topo->nodes[sw_indices[sw_i]].role, "primary") != 0) {
                            strcpy(topo->nodes[sw_indices[sw_i]].role, "backup");
                            strcpy(topo->nodes[sw_indices[sw_i]].subtext, "Backup");
                        }
                    }
                }
                snprintf(pb->name, sizeof(pb->name), "Path-B (%s)", bpath_str);

                for (int i = 0; i < pb->hop_count - 1; i++) {
                    const char *u = pb->hops[i];
                    const char *v = pb->hops[i + 1];
                    for (int e = 0; e < topo->link_count; e++) {
                        TopoLink *lk = &topo->links[e];
                        if ((strcmp(lk->src, u) == 0 && strcmp(lk->dst, v) == 0) ||
                            (strcmp(lk->src, v) == 0 && strcmp(lk->dst, u) == 0)) {
                            if (!lk->path_segment[0]) {
                                strcpy(lk->path_segment, "path_b");
                                lk->is_bottleneck = true;
                                if (strcmp(u, ingress) == 0) strcpy(lk->label, "Path B");
                                else strcpy(lk->label, "Path B (egress)");
                            }
                        }
                    }
                }
            }
        }
    }
}

/* -------------------------------------------------------------------------- */
/* JSON Serializer                                                            */
/* -------------------------------------------------------------------------- */
static void write_topology_json(const Topology *topo, const char *source_filename, FILE *out) {
    fprintf(out, "{\n");
    fprintf(out, "  \"format\": \"network-topology\",\n");
    fprintf(out, "  \"version\": \"1.0\",\n");
    fprintf(out, "  \"topology_name\": \"%s\",\n", topo->topo_name);
    fprintf(out, "  \"description\": \"Generated from %s via TopoNet Compiler\",\n", source_filename);

    // Switches
    fprintf(out, "  \"switches\": [\n");
    bool first_sw = true;
    for (int i = 0; i < topo->node_count; i++) {
        const TopoNode *nd = &topo->nodes[i];
        if (!nd->is_switch) continue;
        if (!first_sw) fprintf(out, ",\n");
        first_sw = false;
        fprintf(out, "    {\n");
        fprintf(out, "      \"id\": \"%s\",\n", nd->id);
        fprintf(out, "      \"dpid\": %d,\n", nd->dpid);
        fprintf(out, "      \"name\": \"%s\",\n", nd->name);
        fprintf(out, "      \"role\": \"%s\",\n", nd->role);
        fprintf(out, "      \"protocols\": \"OpenFlow13\",\n");
        fprintf(out, "      \"subtext\": \"%s\",\n", nd->subtext);
        fprintf(out, "      \"x\": %.2f,\n", nd->x);
        fprintf(out, "      \"y\": %.2f\n", nd->y);
        fprintf(out, "    }");
    }
    fprintf(out, "\n  ],\n");

    // Hosts
    fprintf(out, "  \"hosts\": [\n");
    bool first_h = true;
    for (int i = 0; i < topo->node_count; i++) {
        const TopoNode *nd = &topo->nodes[i];
        if (nd->is_switch) continue;
        if (!first_h) fprintf(out, ",\n");
        first_h = false;
        fprintf(out, "    {\n");
        fprintf(out, "      \"id\": \"%s\",\n", nd->id);
        fprintf(out, "      \"name\": \"%s\",\n", nd->name);
        fprintf(out, "      \"ip\": \"%s\",\n", nd->ip);
        fprintf(out, "      \"role\": \"%s\",\n", nd->role);
        fprintf(out, "      \"subtext\": \"%s\",\n", nd->subtext);
        fprintf(out, "      \"color\": \"%s\",\n", nd->color);
        fprintf(out, "      \"connected_to\": \"%s\",\n", nd->connected_to);
        fprintf(out, "      \"x\": %.2f,\n", nd->x);
        fprintf(out, "      \"y\": %.2f\n", nd->y);
        fprintf(out, "    }");
    }
    fprintf(out, "\n  ],\n");

    // Links
    fprintf(out, "  \"links\": [\n");
    for (int i = 0; i < topo->link_count; i++) {
        const TopoLink *lk = &topo->links[i];
        if (i > 0) fprintf(out, ",\n");
        fprintf(out, "    {\n");
        fprintf(out, "      \"id\": \"%s\",\n", lk->id);
        fprintf(out, "      \"src\": \"%s\",\n", lk->src);
        fprintf(out, "      \"dst\": \"%s\",\n", lk->dst);
        fprintf(out, "      \"label\": \"%s\",\n", lk->label);
        fprintf(out, "      \"bw_mbps\": %.1f,\n", lk->bw_mbps);
        fprintf(out, "      \"delay_ms\": %.1f,\n", lk->delay_ms);
        fprintf(out, "      \"max_queue\": %d,\n", lk->max_queue);
        fprintf(out, "      \"type\": \"%s\",\n", lk->type);
        fprintf(out, "      \"cable_alias\": \"%s\"", lk->cable_alias);
        if (lk->pen_color[0]) {
            fprintf(out, ",\n      \"pen_color\": \"%s\"", lk->pen_color);
        }
        if (lk->path_segment[0]) {
            fprintf(out, ",\n      \"path_segment\": \"%s\"", lk->path_segment);
        }
        if (lk->is_bottleneck) {
            fprintf(out, ",\n      \"is_bottleneck\": true");
        }
        fprintf(out, "\n    }");
    }
    fprintf(out, "\n  ],\n");

    // Paths
    fprintf(out, "  \"paths\": {\n");
    for (int i = 0; i < topo->path_count; i++) {
        const TopoPath *p = &topo->paths[i];
        if (i > 0) fprintf(out, ",\n");
        fprintf(out, "    \"%s\": {\n", p->id);
        fprintf(out, "      \"id\": \"%s\",\n", p->id);
        fprintf(out, "      \"name\": \"%s\",\n", p->name);
        fprintf(out, "      \"role\": \"%s\",\n", p->role);
        fprintf(out, "      \"hops\": [\n");
        for (int h = 0; h < p->hop_count; h++) {
            fprintf(out, "        \"%s\"%s\n", p->hops[h], (h + 1 < p->hop_count) ? "," : "");
        }
        fprintf(out, "      ],\n");
        fprintf(out, "      \"delay_ms\": %.1f,\n", p->delay_ms);
        fprintf(out, "      \"capacity_mbps\": %.1f,\n", p->capacity_mbps);
        fprintf(out, "      \"queue_limit\": %d,\n", p->queue_limit);
        fprintf(out, "      \"s1_output_port\": %d\n", p->s1_output_port);
        fprintf(out, "    }");
    }
    fprintf(out, "\n  },\n");

    // Traffic Profile
    fprintf(out, "  \"traffic_profile\": {\n");
    bool has_main = false;
    for (int i = 0; i < topo->node_count; i++) {
        if (strcmp(topo->nodes[i].id, "h1") == 0) has_main = true;
    }
    if (has_main) {
        fprintf(out, "    \"main_stream\": {\n");
        fprintf(out, "      \"src_host\": \"h1\",\n");
        fprintf(out, "      \"dst_host\": \"h2\",\n");
        fprintf(out, "      \"dst_port\": 9999,\n");
        fprintf(out, "      \"nominal_rate_mbps\": 6.0,\n");
        fprintf(out, "      \"packet_size_bytes\": 1024\n");
        fprintf(out, "    }");
    }
    bool has_cross = false;
    for (int i = 0; i < topo->node_count; i++) {
        if (strcmp(topo->nodes[i].id, "h3") == 0) has_cross = true;
    }
    if (has_cross) {
        if (has_main) fprintf(out, ",\n");
        fprintf(out, "    \"cross_traffic\": {\n");
        fprintf(out, "      \"src_host\": \"h3\",\n");
        fprintf(out, "      \"dst_host\": \"h4\",\n");
        fprintf(out, "      \"dst_port\": 9998,\n");
        fprintf(out, "      \"burst_rate_mbps\": 7.0,\n");
        fprintf(out, "      \"burst_duration_sec\": 9.0,\n");
        fprintf(out, "      \"target_path\": \"path_a\"\n");
        fprintf(out, "    }\n");
    } else {
        if (has_main) fprintf(out, "\n");
    }
    fprintf(out, "  },\n");

    // SDN Policy
    fprintf(out, "  \"sdn_policy\": {\n");
    fprintf(out, "    \"congestion_threshold_mbps\": 8.0,\n");
    fprintf(out, "    \"congestion_loss_threshold_pct\": 3.0,\n");
    fprintf(out, "    \"hysteresis_recovery_mbps\": 4.5,\n");
    fprintf(out, "    \"poll_interval_sec\": 0.5,\n");
    fprintf(out, "    \"consecutive_triggers_required\": 2,\n");
    fprintf(out, "    \"consecutive_recoveries_required\": 4\n");
    fprintf(out, "  }\n");
    fprintf(out, "}\n");
}

/* -------------------------------------------------------------------------- */
/* High-Level Compiler Pipeline                                               */
/* -------------------------------------------------------------------------- */
static bool compile_file(const char *input_path, const char *output_path, const char *forced_type) {
    if (!file_exists(input_path)) {
        fprintf(stderr, "[ERROR] Input file '%s' does not exist.\n", input_path);
        return false;
    }

    StrBuf preprocessed;
    sb_init(&preprocessed);

    char visited[MAX_FILES][MAX_STR];
    int visited_count = 0;

    if (!preprocess_file(input_path, &preprocessed, visited, &visited_count)) {
        fprintf(stderr, "[ERROR] Preprocessing failed for '%s'.\n", input_path);
        sb_free(&preprocessed);
        return false;
    }

    Token *tokens = (Token *)malloc(MAX_TOKENS * sizeof(Token));
    int num_tokens = 0;
    tokenize(preprocessed.data, tokens, &num_tokens);

    ParseResult res;
    parse_tokens(tokens, num_tokens, &res);

    free(tokens);
    sb_free(&preprocessed);

    // Build Topology struct
    Topology topo;
    memset(&topo, 0, sizeof(Topology));

    char base_name[MAX_STR];
    get_basename(input_path, base_name);

    if (res.topology_name[0]) {
        snprintf(topo.topo_name, sizeof(topo.topo_name), "%s Topology", res.topology_name);
        topo.topo_name[0] = toupper((unsigned char)topo.topo_name[0]);
    } else {
        snprintf(topo.topo_name, sizeof(topo.topo_name), "%s Topology", base_name);
        topo.topo_name[0] = toupper((unsigned char)topo.topo_name[0]);
    }

    // Determine layout type
    char layout_type[MAX_STR] = "auto";
    if (forced_type && strcmp(forced_type, "auto") != 0) {
        strncpy(layout_type, forced_type, MAX_STR - 1);
    } else {
        char infer[MAX_STR];
        snprintf(infer, sizeof(infer), "%s %s", base_name, topo.topo_name);
        for (char *c = infer; *c; c++) *c = tolower((unsigned char)*c);
        if (strstr(infer, "diamond")) strcpy(layout_type, "diamond");
        else if (strstr(infer, "star")) strcpy(layout_type, "star");
        else if (strstr(infer, "bus")) strcpy(layout_type, "bus");
        else if (strstr(infer, "ring")) strcpy(layout_type, "ring");
        else if (strstr(infer, "mesh")) strcpy(layout_type, "mesh");
        else strcpy(layout_type, "auto");
    }

    // Instantiate connections & nodes
    for (int c = 0; c < res.conn_count; c++) {
        int u_idx = find_or_add_node(&topo, res.conns[c].src, &res, true);
        int v_idx = find_or_add_node(&topo, res.conns[c].dst, &res, false);

        TopoNode *u = &topo.nodes[u_idx];
        TopoNode *v = &topo.nodes[v_idx];

        // Track connected_to for hosts
        if (!u->is_switch && v->is_switch) {
            strncpy(u->connected_to, v->id, MAX_STR - 1);
        } else if (!v->is_switch && u->is_switch) {
            strncpy(v->connected_to, u->id, MAX_STR - 1);
        }

        if (topo.link_count < MAX_LINKS) {
            TopoLink *lk = &topo.links[topo.link_count++];
            memset(lk, 0, sizeof(TopoLink));
            snprintf(lk->id, sizeof(lk->id), "link_%s_%s", u->id, v->id);
            strncpy(lk->src, u->id, MAX_STR - 1);
            strncpy(lk->dst, v->id, MAX_STR - 1);
            snprintf(lk->label, sizeof(lk->label), "%s->%s", u->name, v->name);
            strncpy(lk->cable_alias, res.conns[c].cable, MAX_STR - 1);

            bool is_host_edge = (!u->is_switch || !v->is_switch);
            if (is_host_edge) {
                strcpy(lk->type, "host_edge");
                lk->bw_mbps = 100.0;
                lk->delay_ms = 1.0;
                lk->max_queue = 1000;
                if (strcmp(u->id, "h1") == 0 || strcmp(v->id, "h1") == 0 ||
                    strcmp(u->id, "h2") == 0 || strcmp(v->id, "h2") == 0) {
                    strcpy(lk->pen_color, "#89b4fa");
                } else if (strcmp(u->id, "h3") == 0 || strcmp(v->id, "h3") == 0 ||
                           strcmp(u->id, "h4") == 0 || strcmp(v->id, "h4") == 0) {
                    strcpy(lk->pen_color, "#f38ba8");
                } else {
                    strcpy(lk->pen_color, "#a6adc8");
                }
            } else {
                strcpy(lk->type, "switch_edge");
                lk->max_queue = 100;
                lk->delay_ms = 5.0;

                char calow[MAX_STR];
                strncpy(calow, lk->cable_alias, MAX_STR - 1);
                for (char *p = calow; *p; p++) *p = tolower((unsigned char)*p);

                if (strstr(calow, "lo") || strstr(calow, "low")) {
                    lk->bw_mbps = 5.0;
                } else {
                    lk->bw_mbps = 10.0;
                }
            }
        }
    }

    // Sort switches and hosts deterministically (s1..sn, h1..hn)
    TopoNode sorted_nodes[MAX_NODES];
    int sn_count = 0;
    for (int i = 0; i < topo.node_count; i++) {
        if (topo.nodes[i].is_switch) sorted_nodes[sn_count++] = topo.nodes[i];
    }
    // simple bubble sort switches by dpid or id
    for (int i = 0; i < sn_count; i++) {
        for (int j = i + 1; j < sn_count; j++) {
            if (sorted_nodes[i].dpid > sorted_nodes[j].dpid ||
                (sorted_nodes[i].dpid == sorted_nodes[j].dpid && strcmp(sorted_nodes[i].id, sorted_nodes[j].id) > 0)) {
                TopoNode tmp = sorted_nodes[i];
                sorted_nodes[i] = sorted_nodes[j];
                sorted_nodes[j] = tmp;
            }
        }
    }
    int sw_boundary = sn_count;
    for (int i = 0; i < topo.node_count; i++) {
        if (!topo.nodes[i].is_switch) sorted_nodes[sn_count++] = topo.nodes[i];
    }
    for (int i = sw_boundary; i < sn_count; i++) {
        for (int j = i + 1; j < sn_count; j++) {
            if (strcmp(sorted_nodes[i].id, sorted_nodes[j].id) > 0) {
                TopoNode tmp = sorted_nodes[i];
                sorted_nodes[i] = sorted_nodes[j];
                sorted_nodes[j] = tmp;
            }
        }
    }
    memcpy(topo.nodes, sorted_nodes, sn_count * sizeof(TopoNode));
    topo.node_count = sn_count;

    // Discover SDN paths A & B
    synthesize_paths(&topo);

    // Apply 2D normalized coordinates
    apply_coordinates(&topo, layout_type);

    // Write output JSON
    make_parent_dir(output_path);
    FILE *out = fopen(output_path, "w");
    if (!out) {
        fprintf(stderr, "[ERROR] Cannot open output file '%s' for writing.\n", output_path);
        return false;
    }

    const char *src_fname = strrchr(input_path, '/');
    const char *src_fname_b = strrchr(input_path, '\\');
    if (src_fname_b && (!src_fname || src_fname_b > src_fname)) src_fname = src_fname_b;
    src_fname = src_fname ? src_fname + 1 : input_path;

    write_topology_json(&topo, src_fname, out);
    fclose(out);

    return true;
}

/* -------------------------------------------------------------------------- */
/* Main CLI Driver                                                            */
/* -------------------------------------------------------------------------- */
int main(int argc, char *argv[]) {
    const char *input_path = NULL;
    const char *output_path = NULL;
    const char *type = "auto";
    bool compile_all = false;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-o") == 0 || strcmp(argv[i], "--output") == 0) {
            if (i + 1 < argc) output_path = argv[++i];
        } else if (strcmp(argv[i], "-t") == 0 || strcmp(argv[i], "--type") == 0) {
            if (i + 1 < argc) type = argv[++i];
        } else if (strcmp(argv[i], "--all") == 0) {
            compile_all = true;
        } else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            printf("Usage: polc <input.pol> [-o <output.json>] [-t <type>]\n");
            printf("       polc --all\n\n");
            printf("Options:\n");
            printf("  -o, --output <file>    Set destination JSON file path\n");
            printf("  -t, --type <type>      Topology layout (diamond, star, ring, bus, mesh, auto)\n");
            printf("  --all                  Compile all .pol files in pol_src/ to topology_src/\n");
            printf("  -h, --help             Show this help message\n");
            return 0;
        } else if (argv[i][0] != '-') {
            input_path = argv[i];
        }
    }

    if (compile_all) {
        const char *known_files[] = {
            "pol_src/diamond.pol",
            "pol_src/star.pol",
            "pol_src/bus.pol",
            "pol_src/ring.pol",
            "pol_src/mesh.pol",
            "pol_src/test.pol"
        };
        int num_files = 6;
        bool all_ok = true;

        for (int i = 0; i < num_files; i++) {
            if (!file_exists(known_files[i])) continue;
            char base[MAX_STR];
            get_basename(known_files[i], base);
            char out_json[512];
            snprintf(out_json, sizeof(out_json), "topology_src/%s.json", base);

            if (compile_file(known_files[i], out_json, type)) {
                printf("[SUCCESS] Compiled %s -> %s\n", known_files[i], out_json);
            } else {
                printf("[ERROR] Failed compiling %s\n", known_files[i]);
                all_ok = false;
            }
        }
        return all_ok ? 0 : 1;
    }

    if (!input_path) {
        fprintf(stderr, "Error: No input file specified. Run 'polc --help' for usage.\n");
        return 1;
    }

    char default_out[512];
    if (!output_path) {
        char base[MAX_STR];
        get_basename(input_path, base);
        snprintf(default_out, sizeof(default_out), "topology_src/%s.json", base);
        output_path = default_out;
    }

    if (compile_file(input_path, output_path, type)) {
        printf("[SUCCESS] Successfully compiled '%s' -> '%s'\n", input_path, output_path);
        return 0;
    } else {
        fprintf(stderr, "[ERROR] Compilation failed for '%s'\n", input_path);
        return 1;
    }
}
