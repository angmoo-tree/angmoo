#[allow(dead_code)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DesktopLaunchMode {
    InstalledProduct,
    ContributorDockerBridge,
}

impl DesktopLaunchMode {
    pub fn current() -> Result<Self, String> {
        #[cfg(feature = "contributor-docker-bridge")]
        {
            if !cfg!(debug_assertions) {
                return Err("contributor_docker_bridge_release_forbidden".to_owned());
            }
            Ok(Self::ContributorDockerBridge)
        }
        #[cfg(not(feature = "contributor-docker-bridge"))]
        {
            Ok(Self::InstalledProduct)
        }
    }

    pub const fn is_contributor_docker_bridge(self) -> bool {
        matches!(self, Self::ContributorDockerBridge)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compile_time_profile_has_one_unambiguous_mode() {
        let mode = DesktopLaunchMode::current().expect("desktop launch mode");
        assert_eq!(
            mode.is_contributor_docker_bridge(),
            cfg!(feature = "contributor-docker-bridge")
        );
    }
}
