const fs = require("node:fs");
const path = require("node:path");
const { withDangerousMod } = require("@expo/config-plugins");
const { mergeContents } = require("@expo/config-plugins/build/utils/generateCode");

const TAG = "bundle-deployment-target";

/**
 * Bumps CocoaPods resource-bundle targets (PrivacyInfo.xcprivacy carriers) to
 * the project's iOS deployment target. Some podspecs (SDWebImage,
 * GTMSessionFetcher, PromisesObjC, etc.) hardcode iOS 9.0/10.0 on their
 * privacy bundles, which triggers "deployment version mismatch" warnings in
 * Xcode 26. Bundles contain no executable code, so bumping their deployment
 * target is safe.
 */
function withBundleDeploymentTarget(config) {
  return withDangerousMod(config, [
    "ios",
    (cfg) => {
      const podfilePath = path.join(cfg.modRequest.platformProjectRoot, "Podfile");
      const src = fs.readFileSync(podfilePath, "utf8");

      const newSrc = `    bundle_deployment_target = podfile_properties['ios.deploymentTarget'] || '15.1'
    installer.pods_project.targets.each do |target|
      if target.respond_to?(:product_type) && target.product_type == 'com.apple.product-type.bundle'
        target.build_configurations.each do |config|
          config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = bundle_deployment_target
        end
      end
    end`;

      const merged = mergeContents({
        src,
        newSrc,
        tag: TAG,
        anchor: /:ccache_enabled => ccache_enabled\?\(podfile_properties\)/,
        offset: 2,
        comment: "#",
      });

      if (!merged.didMerge && !merged.didClear) {
        return cfg;
      }

      fs.writeFileSync(podfilePath, merged.contents);
      return cfg;
    },
  ]);
}

module.exports = withBundleDeploymentTarget;
