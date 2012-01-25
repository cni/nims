# -*- coding: utf-8 -*-
"""
User* related model.

This is where the models used by :mod:`repoze.who` and :mod:`repoze.what` are defined.
"""

import os
import hashlib
import datetime

from elixir import *

from nimsgears.model import metadata, DBSession

__session__ = DBSession
__metadata__ = metadata

__all__ = ['User', 'Group', 'Permission', 'AccessPrivilege', 'Access', 'ResearchGroup', 'Message']


class Group(Entity):

    """Group definition for :mod:`repoze.what`; `group_name` required."""

    id = Field(Unicode(32), primary_key=True)       # translation for group_name set in app_cfg.py
    name = Field(Unicode(255))
    created = Field(DateTime, default=datetime.datetime.now)

    users = ManyToMany('User', onupdate='CASCADE', ondelete='CASCADE')
    permissions = ManyToMany('Permission', onupdate='CASCADE', ondelete='CASCADE')

    def __repr__(self):
        return ('<Group: group_id=%s>' % self.group_id).encode('utf-8')

    def __unicode__(self):
        return self.group_name


class User(Entity):

    """User definition for :mod:`repoze.who`; `user_name` required."""

    id = Field(Unicode(32), primary_key=True)       # translation for user_name set in app_cfg.py
    name = Field(Unicode(255))
    email = Field(Unicode(255), info={'rum': {'field':'Email'}})
    _password = Field(Unicode(128), colname='password', info={'rum': {'field':'Password'}}, synonym='password')
    created = Field(DateTime, default=datetime.datetime.now)

    groups = ManyToMany('Group', onupdate='CASCADE', ondelete='CASCADE')

    accesses = OneToMany('Access')
    research_groups = ManyToMany('ResearchGroup', inverse='members')
    admin_groups = ManyToMany('ResearchGroup', inverse='admins')
    pi_groups = ManyToMany('ResearchGroup', inverse='pis')
    messages = OneToMany('Message', inverse='recipient')

    def __repr__(self):
        return ('<User: %s, %s, "%s">' % (self.id, self.email, self.name)).encode('utf-8')

    def __unicode__(self):
        return self.name or self.id

    @classmethod
    def by_email_address(cls, email):
        """Return the user object whose email address is ``email``."""
        return cls.query.filter_by(email=email).first()

    @classmethod
    def by_id(cls, username):
        """Return the user object whose user name is ``username``."""
        return cls.query.filter_by(id=username).first()

    @staticmethod
    def _hash_password(password):
        # Make sure password is a str because we cannot hash unicode objects
        if isinstance(password, unicode):
            password = password.encode('utf-8')
        salt = hashlib.sha256()
        salt.update(os.urandom(60))
        hash = hashlib.sha256()
        hash.update(password + salt.hexdigest())
        password = salt.hexdigest() + hash.hexdigest()
        # Make sure the hashed password is a unicode object at the end of the
        # process because SQLAlchemy _wants_ unicode objects for Unicode cols
        if not isinstance(password, unicode):
            password = password.decode('utf-8')
        return password

    def _set_password(self, password):
        """Hash ``password`` on the fly and store its hashed version."""
        self._password = self._hash_password(password)
    def _get_password(self):
        """Return the hashed version of the password."""
        return self._password
    password = property(_get_password, _set_password)

    def validate_password(self, password):
        """Check the password against existing credentials."""
        hash = hashlib.sha256()
        if isinstance(password, unicode):
            password = password.encode('utf-8')
        hash.update(password + str(self.password[:64]))
        return self.password[64:] == hash.hexdigest()

    @property
    def permissions(self):
        """Return a set with all permissions granted to the user."""
        perms = set()
        for g in self.groups:
            perms = perms | set(g.permissions)
        return perms

    @property
    def unread_msg_cnt(self):
        return 8 #len([msg for msg in self.messages if not msg.read]) if self.messages else 0

    @property
    def dataset_cnt(self):
        # FIXME: get the correct count
        # FIXME: make the retrieved sessions available globally, so that they only have to be rerieved once per page loading
        #        in header template: check if info already available, else query (like pagename check)
        return len(self.accesses)


class Permission(Entity):

    """Permission definition for :mod:`repoze.what`; `permission_name` required."""

    id = Field(Unicode(32), primary_key=True)       # translation for user_name set in app_cfg.py
    name = Field(Unicode(255))

    groups = ManyToMany('Group', onupdate='CASCADE', ondelete='CASCADE')

    def __repr__(self):
        return ('<Permission: name=%s>' % self.perm_id).encode('utf-8')

    def __unicode__(self):
        return self.perm_id


class AccessPrivilege(Entity):

    value = Field(Integer, required=True)
    name = Field(Unicode(32), required=True)
    description = Field(Unicode(255))

    access = OneToMany('Access')

    def __unicode__(self):
        return self.name


class Access(Entity):

    user = ManyToOne('User')
    experiment = ManyToOne('Experiment')
    privilege = ManyToOne('AccessPrivilege')

    def __unicode__(self):
        return self.privilege


class ResearchGroup(Entity):

    id = Field(Unicode(31), primary_key=True)
    name = Field(Unicode(255))

    pis = ManyToMany('User', inverse='pi_groups')
    admins = ManyToMany('User', inverse='admins')
    members = ManyToMany('User', inverse='research_groups')

    def __unicode__(self):
        return self.name or self.id


class Message(Entity):

    subject = Field(Unicode(255), required=True)
    body = Field(Unicode)
    priority = Field(Enum(u'normal', u'high', name=u'priority'), default=u'normal')
    created = Field(DateTime, default=datetime.datetime.now)
    read = Field(DateTime)

    recipient = ManyToOne('User', inverse='messages')

    def __repr__(self):
        return ('<Message: "%s: %s", prio=%s>' % (self.recipient, self.subject, self.priority)).encode('utf-8')

    def __unicode__(self):
        return u'%s: %s' % (self.recipient, self.subject)
