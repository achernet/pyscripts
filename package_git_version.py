#!/usr/bin/env python
import sh
import re
import sys
from argparse import ArgumentParser
from path import Path


class TagQuery(object):
    """
    Class to encapsulate searching for Git versioning information.
    """

    def __init__(self, repo_tree_path):
        """
        Set up a new query using the local Git repository that ``repo_tree_path`` is contained in.

        :param str repo_tree_path: Any relative or absolute path inside of a local Git clone.
        """
        self.repo_path = Path(repo_tree_path).expand().abspath()
        self.hash_rgx = re.compile("([0-9a-f]+).*tag:\\s([^),]+)")
        self.num_rgx = re.compile("^[^0-9]+")
        self.git_cmd = sh.Command("git")

    def commit_tags(self):
        """
        Get the list of dicts containing contextual information for each tag defined across the entire repository.

        :return list: A list of ``CommitTag`` objects
        """
        log_out = self.git_cmd("log", "--all", {"format": "%H|%d"}, "--decorate", "--topo-order",
                               "--simplify-by-decoration", _cwd=self.repo_path, _tty_out=False).stdout
        tags = []
        all_revisions = self.git_cmd("rev-list", "--topo-order", "--all",
                                     _cwd=self.repo_path, _tty_out=False).stdout.splitlines()
        for match in self.hash_rgx.finditer(log_out):
            next_tag = {"tag": match.group(2), "commit": match.group(1)}
            try:
                next_tag["index"] = all_revisions.index(next_tag["commit"])
            except ValueError:
                next_tag["index"] = -1
            tag_version = self.num_rgx.sub("", next_tag["tag"])
            if not tag_version.strip() or next_tag["index"] == -1:
                continue
            next_tag["version"] = "{0}-{1}".format(tag_version, next_tag["index"])
            tags.append(next_tag)
        return tags

    def latest_version(self):
        """
        Return a string representing the latest version in the repository.
        TODO: If some old commit is checked out instead of HEAD, this should change accordingly.

        :return str: The latest version according to the state of the Git repository
        """
        all_tags = self.commit_tags()
        all_tags.sort(key=lambda tag: tag["index"])
        if all_tags:
            return all_tags[0]["version"]
        exc_msg = "There must be at least one tag containing a valid version spec (i.e. one or more numbers)!"
        raise Exception(exc_msg)


def version_from_repo(input_repo_path):
    """
    Generate a package version for the Git repository containing ``input_repo_path``.

    :param input_repo_path: The input repository path
    :type input_repo_path: ``path.Path``
    :return str: The latest version (e.g. ``0.4.2a-0``), which should be ``distutils``-compatible.
    """
    tag_query = TagQuery(input_repo_path)
    return tag_query.latest_version()


def main(args=None):
    """
    Entry point for determining the version of a package based on the Git repository it resides in.

    :param list args: The list of arguments
    """
    args = args or sys.argv[1:]
    ap = ArgumentParser(description="Determine the version of a package based on the Git repository it resides in.")
    ap.add_argument("path", type=Path, default="./", help="A path inside the local repository checkout")
    ns = ap.parse_args(args)
    repo_version = version_from_repo(ns.path)
    sys.stdout.write("Latest package version for path {0!r}: {1}\n".format(ns.path, repo_version))


if __name__ == "__main__":  # pragma: no cover
    main()
