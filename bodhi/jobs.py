# $Id: $
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

"""
    This module is for functions that are to be executed on a regular basis
    using the TurboGears scheduler.
"""

import os
import shutil
import logging

from os.path import isdir, realpath, dirname, join, islink
from datetime import datetime
from turbogears import scheduler, config
from sqlobject.sqlbuilder import AND

from bodhi import mail
from bodhi.util import get_age_in_days
from bodhi.model import Release, PackageUpdate

log = logging.getLogger(__name__)

def clean_repo():
    """
    Clean up our mashed_dir, removing all referenced repositories
    """
    log.info("Starting clean_repo job")
    liverepos = []
    repos = config.get('mashed_dir')
    for release in [rel.name.lower() for rel in Release.select()]:
        for repo in [release + '-updates', release + '-updates-testing']:
            liverepos.append(dirname(realpath(join(repos, repo))))
    for repo in [join(repos, repo) for repo in os.listdir(repos)]:
        if not islink(repo) and isdir(repo):
            fullpath = realpath(repo)
            if fullpath not in liverepos:
                log.info("Removing %s" % fullpath)
                shutil.rmtree(fullpath)

def nagmail():
    # Nag submitters when their update has been sitting in testing for more
    # than two weeks.
    name = 'old_testing'
    for update in PackageUpdate.select(
                    AND(PackageUpdate.q.status == 'testing',
                        PackageUpdate.q.request != 'stable')):
        if get_age_in_days(update.date_pushed) > 14:
            if update.nagged.has_key(name) and update.nagged[name]:
                log.debug("%s has nagged[%s] = %s" % (update.title, name,
                          update.nagged[name]))
                if (datetime.utcnow() - update.nagged[name]).days < 7:
                    log.debug("Skipping %s nagmail for %s; less than 7 days " 
                              "since our last nag" % (name, update.title))
                    continue
            log.info("Nagging %s about testing update %s" % (update.submitter,
                     update.title))
            mail.send(update.submitter, name, update)
            nagged = update.nagged
            nagged[name] = datetime.utcnow()
            update.nagged = nagged

def fix_bug_titles():
    """
    Go through all bugs with invalid titles and see if we can re-fetch them.
    If bugzilla is down, then bodhi simply replaces the title with
    'Unable to fetch bug title' or 'Invalid bug number'.  So lets occasionally
    see if we can re-fetch those bugs.
    """
    from bodhi.model import Bugzilla
    from sqlobject.sqlbuilder import OR
    log.debug("Running fix_bug_titles job")
    for bug in Bugzilla.select(
                 OR(Bugzilla.q.title == 'Invalid bug number',
                    Bugzilla.q.title == 'Unable to fetch bug title')):
        bug._fetch_details()

    # Nag submitters if their update has been sitting unsubmitted in a pending
    # state for longer than a week.
    # TODO: implement this once the current 'pending' situation is under
    # control.  Right now, with our production instance, unpushed updates go
    # back into this state -- and we don't want to nag about those.

def schedule():
    """ Schedule our periodic tasks """

    # Weekly repository cleanup
    scheduler.add_interval_task(action=clean_repo,
                                taskname='Repository Cleanup',
                                initialdelay=604800,
                                interval=604800)

    # Weekly nagmail
    scheduler.add_interval_task(action=nagmail,
                                taskname='Nagmail',
                                initialdelay=0,
                                interval=604800)

    # Fix invalid bug titles
    scheduler.add_interval_task(action=fix_bug_titles,
                                taskname='Fix bug titles',
                                initialdelay=0,
                                interval=604800)
