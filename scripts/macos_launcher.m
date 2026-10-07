// Retain the native app PID while the ordinary cadmetrics-gui entry point runs.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int fail(NSString *message) {
    fprintf(stderr, "Cadmetrics launcher: %s\n", message.UTF8String);
    return 1;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        NSURL *resources = NSBundle.mainBundle.resourceURL;
        NSData *configData = [NSData dataWithContentsOfURL:
            [resources URLByAppendingPathComponent:@"launcher.json"]];
        id config = configData ? [NSJSONSerialization JSONObjectWithData:configData
            options:0 error:nil] : nil;
        if (![config isKindOfClass:NSDictionary.class]
            || ![config[@"repo"] isKindOfClass:NSString.class])
            return fail(@"Missing or invalid launcher.json; rebuild this app.");
        NSString *root = [resources.path stringByAppendingPathComponent:config[@"repo"]]
            .stringByStandardizingPath;
        if (chdir(root.fileSystemRepresentation) != 0)
            return fail(@"Cannot enter the checkout directory; rebuild this app.");
        const char *oldPath = getenv("PATH");
        NSString *path = [@"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:"
            stringByAppendingString:oldPath ? @(oldPath) : @""];
        setenv("PATH", path.UTF8String, 1);

        NSFileManager *files = NSFileManager.defaultManager;
        NSString *entry = [root stringByAppendingPathComponent:@".venv/bin/cadmetrics-gui"];
        NSString *python = [root stringByAppendingPathComponent:@".venv/bin/python"];
        NSString *probe = [resources.path stringByAppendingPathComponent:@"macos_runtime.py"];
        NSTask *task = [[NSTask alloc] init];
        BOOL useUv = ![files isExecutableFileAtPath:entry];
        if (!useUv) {
            task.executableURL = [NSURL fileURLWithPath:python];
            task.arguments = @[@"-I", probe];
        } else {
            task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/env"];
            // Preserve the old uv run policy; do not add --locked or synchronize extras.
            task.arguments = @[@"uv", @"run", @"python", @"-I", probe];
        }
        task.currentDirectoryURL = [NSURL fileURLWithPath:root];
        NSPipe *output = [NSPipe pipe];
        task.standardOutput = output;
        task.standardError = NSFileHandle.fileHandleWithStandardError;
        NSError *error = nil;
        if (![task launchAndReturnError:&error])
            return fail([@"Cannot discover Python: " stringByAppendingString:error.localizedDescription]);
        NSData *data = [output.fileHandleForReading readDataToEndOfFile];
        [task waitUntilExit];
        if (task.terminationStatus != 0)
            return fail(@"Python discovery failed; prepare the environment with uv sync --extra step --extra gui.");
        id info = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
        if (![info isKindOfClass:NSDictionary.class]
            || ![info[@"executable"] isKindOfClass:NSString.class]
            || ![info[@"library"] isKindOfClass:NSString.class]
            || ![info[@"entry"] isKindOfClass:NSString.class]
            || ![info[@"path"] isKindOfClass:NSString.class]
            || (info[@"virtual_env"] != NSNull.null
                && ![info[@"virtual_env"] isKindOfClass:NSString.class]))
            return fail(@"Python discovery returned invalid runtime information.");
        if (useUv) {
            // uv configures these for its child; carry them into the native GUI process.
            setenv("PATH", [info[@"path"] UTF8String], 1);
            if (info[@"virtual_env"] == NSNull.null)
                unsetenv("VIRTUAL_ENV");
            else
                setenv("VIRTUAL_ENV", [info[@"virtual_env"] UTF8String], 1);
        }
        python = info[@"executable"];
        NSString *library = info[@"library"];
        entry = info[@"entry"];
        if (![files isExecutableFileAtPath:python] || ![files fileExistsAtPath:library]
            || ![files isExecutableFileAtPath:entry])
            return fail(@"The discovered Python runtime or GUI entry point is no longer available.");
        void *handle = dlopen(library.fileSystemRepresentation, RTLD_NOW | RTLD_GLOBAL);
        if (!handle)
            return fail([NSString stringWithFormat:@"Cannot load Python: %s", dlerror()]);
        int (*pythonMain)(int, char **) = (int (*)(int, char **))dlsym(handle, "Py_BytesMain");
        if (!pythonMain)
            return fail(@"The Python library does not export Py_BytesMain.");
        char **pythonArgs = calloc((size_t)argc + 2, sizeof(char *));
        if (!pythonArgs)
            return fail(@"Cannot allocate Python arguments.");
        // Spawned workers must use the real interpreter, not recursively launch the app.
        pythonArgs[0] = (char *)python.fileSystemRepresentation;
        pythonArgs[1] = (char *)entry.fileSystemRepresentation;
        int count = 2;
        for (int i = 1; i < argc; ++i) {
            if (strncmp(argv[i], "-psn_", 5) != 0)
                pythonArgs[count++] = argv[i];
        }
        int status = pythonMain(count, pythonArgs);
        free(pythonArgs);
        // Keep the library loaded for extension-module/static destructors.
        return status;
    }
}
