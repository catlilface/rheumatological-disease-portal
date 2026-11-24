-- Fixture for the kind upgrade check: databases from the original scaffold.
-- Not mounted by postgres.yaml; up.sh uses the shared bootstrap/dbmate jobs.
CREATE DATABASE content;
CREATE DATABASE screening;
CREATE DATABASE reporting;
CREATE DATABASE files;
CREATE DATABASE iam;
CREATE DATABASE ai;
