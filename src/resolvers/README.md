# Resolvers

Resolvers implement URL resolution strategies. Each resolver returns either a `CompanyRecord` or an `UnresolvedRecord`.

## Files
- `base.py`: abstract `BaseResolver` interface.
- `direct_resolver.py`: resolves ATS URLs to corporate URLs by validating ATS roots and extracting company metadata.
- `breadcrumb_resolver.py`: normalizes job URLs to ATS roots and forwards to `DirectResolver`, avoiding duplicate roots.
- `reverse_resolver.py`: starts from corporate homepages to discover ATS URLs via links, iframes, and job pages.
- `careers_resolver.py`: specialized resolver to derive corporate careers URLs from ATS roots with evidence tracking.
- `phase1_careers_resolver.py`: crawler-based discovery of careers URLs starting from company websites.
- `phase2_ats_resolver.py`: ATS provider detection from careers URLs using domain and HTML markers.
- `__init__.py`: package marker.
