# One git repository per Bundle

Each Bundle (one project's knowledge) is its own git repository with its own remote, rather than a folder in a shared knowledge-base repo. Projects stay isolated, can sit in different GitLab groups with different access, and agents clone only the Bundle they need. The cost is no cross-Bundle links and one remote to configure per Bundle.
