"""Interactive operator provisioning; never put the password in argv or logs."""
import argparse
from getpass import getpass

from .main import authority


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('role', choices=('admin', 'editor'))
    args = parser.parse_args()
    email = input('Staff email: ').strip()
    password = getpass('New password (12–256 characters): ')
    authority().provision(email, password, args.role)


if __name__ == '__main__':
    main()
