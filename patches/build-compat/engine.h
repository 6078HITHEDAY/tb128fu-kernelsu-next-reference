/*
 * Compatibility shim for building old kernels against OpenSSL >= 3.5,
 * which no longer ships <openssl/engine.h>.  The ENGINE symbols are still
 * exported by libcrypto; only the declarations used by extract-cert.c are
 * provided here.
 */
#ifndef OPENSSL_ENGINE_H
#define OPENSSL_ENGINE_H

#include <openssl/types.h>   /* typedef struct engine_st ENGINE; */

#ifdef __cplusplus
extern "C" {
#endif

void ENGINE_load_builtin_engines(void);
ENGINE *ENGINE_by_id(const char *id);
int ENGINE_init(ENGINE *e);
int ENGINE_ctrl_cmd_string(ENGINE *e, const char *cmd, const char *arg,
                           int optional);
int ENGINE_ctrl_cmd(ENGINE *e, const char *cmd, long i, void *p,
                    void (*f)(void), int optional);

#ifdef __cplusplus
}
#endif

#endif /* OPENSSL_ENGINE_H */
