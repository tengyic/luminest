#!/usr/bin/env python3
import hashlib
import json
import plistlib
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PROJECT = HERE / 'NativeHarnessUI.xcodeproj'


def uid(name):
    return hashlib.sha256(name.encode()).hexdigest()[:24].upper()


def quote(value):
    return json.dumps(str(value))


def generate(port=8766):
    objects = {}

    def add(name, content):
        key = uid(name)
        objects[key] = '{ ' + content + ' };'
        return key

    def refs(values):
        return '(' + ', '.join(values) + ',)'

    base = ROOT / 'harness/native/Sources/LearningHarness'
    # Recursive on purpose: the sources are organised into Shared/ and Features/, and a
    # non-recursive glob silently dropped every file below the top level — the UI test
    # target still built, against a subset of the app, and nothing reported the omission.
    sources = sorted(base.rglob('*.swift'))
    if not sources:
        raise RuntimeError('No native application Swift sources found')
    native_refs, native_build, by_directory = [], [], {}
    for source in sources:
        relative = source.relative_to(base).as_posix()
        # The identity key carries the subpath for the same reason: two files in different
        # directories can share a basename, and a `uid` collision would fold them into one
        # build entry — one of them compiled, the other silently absent.
        ref = add('source:' + relative, 'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = ' + quote('../../native/Sources/LearningHarness/' + relative) + '; sourceTree = "<group>";')
        native_refs.append(ref)
        native_build.append(add('build:' + relative, f'isa = PBXBuildFile; fileRef = {ref};'))
        by_directory.setdefault(relative.rsplit('/', 1)[0] if '/' in relative else '', []).append(ref)
    # Virtual groups (no `path`) so their children keep resolving through the parent group's
    # `path = Tests`, which is what makes the "../../native/..." references line up.
    directory_groups = [
        add('nativegroup:' + directory,
            f'isa = PBXGroup; name = {quote(directory)}; sourceTree = "<group>"; children = ' + refs(by_directory[directory]) + ';')
        for directory in sorted(by_directory) if directory
    ]
    test_ref = add('testsource', 'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = NativeWorkflowTests.swift; sourceTree = "<group>";')
    test_build = add('testbuild', f'isa = PBXBuildFile; fileRef = {test_ref};')
    configuration_ref = add('runnerconfig', 'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = RunnerConfiguration.swift; sourceTree = "<group>";')
    configuration_build = add('runnerconfigbuild', f'isa = PBXBuildFile; fileRef = {configuration_ref};')
    app_product = add('appproduct', 'isa = PBXFileReference; explicitFileType = wrapper.application; path = LearningHarnessUITarget.app; sourceTree = BUILT_PRODUCTS_DIR;')
    test_product = add('testproduct', 'isa = PBXFileReference; explicitFileType = wrapper.cfbundle; path = NativeHarnessUITests.xctest; sourceTree = BUILT_PRODUCTS_DIR;')
    native_group = add('nativegroup', 'isa = PBXGroup; name = NativeSources; path = Tests; sourceTree = "<group>"; children = ' + refs(by_directory.get('', []) + directory_groups) + ';')
    tests_group = add('testgroup', f'isa = PBXGroup; path = Tests; sourceTree = "<group>"; children = ({test_ref}, {configuration_ref},);')
    products_group = add('productgroup', f'isa = PBXGroup; name = Products; sourceTree = "<group>"; children = ({app_product}, {test_product},);')
    main_group = add('main', f'isa = PBXGroup; sourceTree = "<group>"; children = ({native_group}, {tests_group}, {products_group},);')
    app_target, test_target, project_id = uid('apptarget'), uid('testtarget'), uid('project')
    proxy = add('proxy', f'isa = PBXContainerItemProxy; containerPortal = {project_id}; proxyType = 1; remoteGlobalIDString = {app_target}; remoteInfo = LearningHarnessUITarget;')
    dependency = add('dependency', f'isa = PBXTargetDependency; target = {app_target}; targetProxy = {proxy};')

    interop_ref = add('testinginterop', 'isa = PBXFileReference; lastKnownFileType = compiled.mach-o.dylib; path = Platforms/MacOSX.platform/Developer/usr/lib/lib_TestingInterop.dylib; sourceTree = DEVELOPER_DIR;')
    interop_build = add('testinginteropbuild', f'isa = PBXBuildFile; fileRef = {interop_ref}; settings = {{ ATTRIBUTES = (CodeSignOnCopy,); }};')
    interop_phase = add('testinginteropcopy', f'isa = PBXCopyFilesBuildPhase; buildActionMask = 2147483647; dstPath = "$(TARGET_BUILD_DIR)/../Frameworks"; dstSubfolderSpec = 0; files = ({interop_build},); name = "Embed Xcode Testing Interop"; runOnlyForDeploymentPostprocessing = 0;')

    def phases(name, builds):
        source_phase = add(name + 'sources', 'isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ' + refs(builds) + '; runOnlyForDeploymentPostprocessing = 0;')
        frameworks = add(name + 'frameworks', 'isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0;')
        resources = add(name + 'resources', 'isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0;')
        return refs([source_phase, frameworks, resources] + ([interop_phase] if name == 'test' else []))

    def configurations(name, extra):
        configs = []
        for config in ('Debug', 'Release'):
            settings = {
                'SDKROOT': 'macosx', 'SUPPORTED_PLATFORMS': 'macosx',
                'MACOSX_DEPLOYMENT_TARGET': '14.0', 'SWIFT_VERSION': '5.0',
                'CLANG_ENABLE_MODULES': 'YES', 'CODE_SIGN_IDENTITY': '-',
                'CODE_SIGN_STYLE': 'Manual', 'CODE_SIGNING_ALLOWED': 'YES',
                'CODE_SIGNING_REQUIRED': 'YES', 'ENABLE_HARDENED_RUNTIME': 'NO',
                # Ad-hoc signed (CODE_SIGN_IDENTITY "-") and therefore has no provisioning
                # profile. A sandboxed ad-hoc app cannot be granted a container, so libsecinit
                # traps in _libsecinit_appsandbox during dyld initialisers and the XCTest runner
                # dies with "exited with code 1 before establishing connection". Turning the
                # sandbox off for the test host and runner is what makes Layer 3 runnable here.
                'ENABLE_APP_SANDBOX': 'NO',
                'SWIFT_OPTIMIZATION_LEVEL': '-Onone' if config == 'Debug' else '-O',
                'ENABLE_TESTABILITY': 'YES', 'DEBUG_INFORMATION_FORMAT': 'dwarf',
            }
            settings.update(extra)
            encoded = ' '.join(f'{key} = {quote(value)};' for key, value in sorted(settings.items()))
            configs.append(add(name + config, f'isa = XCBuildConfiguration; name = {config}; buildSettings = {{ {encoded} }};'))
        return add(name + 'configs', 'isa = XCConfigurationList; buildConfigurations = ' + refs(configs) + '; defaultConfigurationIsVisible = 0; defaultConfigurationName = Debug;')

    project_config = configurations('project', {})
    app_config = configurations('app', {
        'PRODUCT_NAME': 'LearningHarnessUITarget', 'PRODUCT_BUNDLE_IDENTIFIER': 'com.luminfest.learningharness.uitarget',
        'GENERATE_INFOPLIST_FILE': 'YES', 'INFOPLIST_FILE': 'Application-Info.plist',
        'INFOPLIST_KEY_CFBundleDisplayName': 'Luminfest Learning Harness UI Target',
        'MARKETING_VERSION': '1.0', 'CURRENT_PROJECT_VERSION': '1',
        'LD_RUNPATH_SEARCH_PATHS': '$(inherited) @executable_path/../Frameworks',
    })
    test_config = configurations('test', {
        'PRODUCT_NAME': 'NativeHarnessUITests', 'PRODUCT_BUNDLE_IDENTIFIER': 'com.luminfest.learningharness.uitarget.ui',
        'GENERATE_INFOPLIST_FILE': 'YES', 'TEST_TARGET_NAME': 'LearningHarnessUITarget',
        'LD_RUNPATH_SEARCH_PATHS': '$(inherited) @executable_path/../Frameworks @loader_path/../../../../Frameworks $(PLATFORM_DIR)/Developer/Library/Frameworks $(PLATFORM_DIR)/Developer/Library/PrivateFrameworks $(PLATFORM_DIR)/Developer/usr/lib',
    })
    add('apptarget', f'isa = PBXNativeTarget; name = LearningHarnessUITarget; productName = LearningHarnessUITarget; productReference = {app_product}; productType = "com.apple.product-type.application"; buildConfigurationList = {app_config}; buildPhases = {phases("app", native_build)}; buildRules = (); dependencies = ();')
    add('testtarget', f'isa = PBXNativeTarget; name = NativeHarnessUITests; productName = NativeHarnessUITests; productReference = {test_product}; productType = "com.apple.product-type.bundle.ui-testing"; buildConfigurationList = {test_config}; buildPhases = {phases("test", [test_build, configuration_build])}; buildRules = (); dependencies = ({dependency},);')
    add('project', f'isa = PBXProject; attributes = {{ LastUpgradeCheck = 2600; TargetAttributes = {{ {app_target} = {{ CreatedOnToolsVersion = 26.0; }}; {test_target} = {{ CreatedOnToolsVersion = 26.0; TestTargetID = {app_target}; }}; }}; }}; buildConfigurationList = {project_config}; compatibilityVersion = "Xcode 14.0"; developmentRegion = en; knownRegions = (en, Base,); mainGroup = {main_group}; productRefGroup = {products_group}; projectDirPath = ""; projectRoot = ""; targets = ({app_target}, {test_target},);')
    project_text = '// !$*UTF8*$!\n{ archiveVersion = 1; classes = {}; objectVersion = 56; objects = {\n'
    project_text += '\n'.join(f'{key} = {objects[key]}' for key in sorted(objects))
    project_text += f'\n}}; rootObject = {project_id}; }}\n'
    (PROJECT / 'project.pbxproj').write_text(project_text)
    with (HERE / 'Application-Info.plist').open('wb') as stream:
        plistlib.dump({'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True}, 'LSApplicationCategoryType': 'public.app-category.education'}, stream)

    def buildable(target, name, product):
        return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="{product}" BlueprintName="{name}" ReferencedContainer="container:NativeHarnessUI.xcodeproj"/>'

    app = buildable(app_target, 'LearningHarnessUITarget', 'LearningHarnessUITarget.app')
    test = buildable(test_target, 'NativeHarnessUITests', 'NativeHarnessUITests.xctest')
    scheme = f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2600" version="1.3">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries>
<BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="NO" buildForArchiving="NO" buildForAnalyzing="YES">{app}</BuildActionEntry>
<BuildActionEntry buildForTesting="YES" buildForRunning="NO" buildForProfiling="NO" buildForArchiving="NO" buildForAnalyzing="YES">{test}</BuildActionEntry>
</BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="NO">
<Testables><TestableReference skipped="NO" parallelizable="NO">{test}</TestableReference></Testables>
<EnvironmentVariables><EnvironmentVariable key="HARNESS_UI_OUTPUT" value="{escape(str(ROOT / 'outputs/ui'), {'"': '&quot;'})}" isEnabled="YES"/>
<EnvironmentVariable key="HARNESS_UI_ENDPOINT" value="http://127.0.0.1:{port}" isEnabled="YES"/></EnvironmentVariables>
</TestAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="YES" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0">{app}</BuildableProductRunnable><CommandLineArguments><CommandLineArgument argument="--ui-test" isEnabled="YES"/></CommandLineArguments></LaunchAction>
<AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>'''
    (PROJECT / 'xcshareddata/xcschemes/NativeHarnessUI.xcscheme').write_text(scheme)
    return [str(source.relative_to(ROOT)) for source in sources]


if __name__ == '__main__':
    print(json.dumps({'project': str(PROJECT), 'sources': generate()}, indent=2))
