# @author:  Gunnar Schaefer

from nimsgears.lib.base import BaseController
from nimsgears.controllers.browse import BrowseController
from nimsgears.controllers.search import SearchController

__all__ = ['PubController']


class PubController(BaseController):

    browse = BrowseController()
    #search = SearchController()
