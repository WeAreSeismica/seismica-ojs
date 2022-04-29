# seismica-ojs: files and scripts related to the Seismica OJS website

## stylesheet.css
Custom css for the website, to be layered on top of a theme (likely a bootstrap variant)

## guidelines parsing
The Guidelines for Authors, Reviewers and Editors, and the Editorial Policies, currently live in google docs. The script `parse_google_doc.py` is a first attempt at translating those documents into convenient html with collapsible headings for display on the OJS site. 

The input to the script is a google-exported html file for either of the docs.

The current version of the script is a bit brittle because google apparently does a terrible job of converting rich text formatting to html, and the two documents we're working with here have different (and in some places oddly specific) text formatting.

### dependencies
- [BeautifulSoup 4](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- numpy
- [cssutils](https://cthedot.de/cssutils/)
- re, os, sys, copy, argparse
