#include "quickjs-libc.h"
#include "quickjs.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static JSRuntime *rt = NULL;
static JSContext *ctx = NULL;
static int nbinterrupts = 0;

static int interrupt_handler(JSRuntime *rt, void *opaque) {
    nbinterrupts++;
    return (nbinterrupts > 100);
}

static void initialize(void) {
    rt = JS_NewRuntime();
    if (!rt) {
        return;
    }
    /* Limit memory to 64MB */
    JS_SetMemoryLimit(rt, 0x4000000);
    JS_SetInterruptHandler(rt, interrupt_handler, NULL);

    ctx = JS_NewContext(rt);
    if (!ctx) {
        JS_FreeRuntime(rt);
        rt = NULL;
        return;
    }

    JS_AddIntrinsicBaseObjects(ctx);
    JS_AddIntrinsicDate(ctx);
    JS_AddIntrinsicEval(ctx);
    JS_AddIntrinsicStringNormalize(ctx);
    JS_AddIntrinsicRegExp(ctx);
    JS_AddIntrinsicJSON(ctx);
    JS_AddIntrinsicProxy(ctx);
    JS_AddIntrinsicMapSet(ctx);
    JS_AddIntrinsicTypedArrays(ctx);
    JS_AddIntrinsicPromise(ctx);
    JS_AddIntrinsicBigInt(ctx);

    js_std_add_helpers(ctx, 0, NULL);
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    JSValue val;
    char *script = NULL;

    if (rt == NULL || ctx == NULL) {
        initialize();
        if (rt == NULL || ctx == NULL) {
            return 0;
        }
    }

    if (size == 0) {
        return 0;
    }

    /* Create a null-terminated copy of the input */
    script = (char *)malloc(size + 1);
    if (!script) {
        return 0;
    }
    memcpy(script, data, size);
    script[size] = '\0';

    /* Reset interrupt counter */
    nbinterrupts = 0;

    /* Try global eval */
    val = JS_Eval(ctx, script, size, "<fuzz>", JS_EVAL_TYPE_GLOBAL);
    if (!JS_IsException(val)) {
        js_std_loop(ctx);
    } else {
        /* Clear exception */
        JSValue exc = JS_GetException(ctx);
        JS_FreeValue(ctx, exc);
    }
    JS_FreeValue(ctx, val);

    /* Reset interrupt counter */
    nbinterrupts = 0;

    /* Try module eval */
    val = JS_Eval(ctx, script, size, "<fuzz_module>", JS_EVAL_TYPE_MODULE | JS_EVAL_FLAG_COMPILE_ONLY);
    if (!JS_IsException(val)) {
        JS_FreeValue(ctx, val);
    } else {
        JSValue exc = JS_GetException(ctx);
        JS_FreeValue(ctx, exc);
    }

    /* Reset interrupt counter */
    nbinterrupts = 0;

    /* Try compile-only eval */
    val = JS_Eval(ctx, script, size, "<fuzz_compile>", JS_EVAL_FLAG_COMPILE_ONLY | JS_EVAL_TYPE_GLOBAL);
    if (!JS_IsException(val)) {
        JS_FreeValue(ctx, val);
    } else {
        JSValue exc = JS_GetException(ctx);
        JS_FreeValue(ctx, exc);
    }

    free(script);
    return 0;
}