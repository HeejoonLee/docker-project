# No authentication by design

Stonepedia runs on a trusted company intranet and has no login, TLS or secrets of its own. A Reviewer is identified only by a self-chosen display name, stored in the browser, used as the git commit author and recorded in the Article's review metadata. This is accountability, not security; anyone who can reach the port can do anything. Do not add auth without revisiting this decision.
