# boxkit: generated implementation of `sidebar` against spec 363d56fe0035c8a5


def _person_label(p: Actor, esc: Escape) -> str:
    label = p.name + " (" + p.role
    if p.org:
        label = label + " · " + p.org
    label = label + ")"
    return esc(label)


def sidebar(current: QueueKey | None, oob: bool, desk: DeskReader, sort: QueueSorter, esc: Escape) -> str:
    queues = sort(desk.cases(), desk.today())
    me = desk.me()

    links = []
    for q in queues:
        key = esc(q.key)
        cls = "nav-link"
        if current is not None and q.key == current:
            cls = cls + " current"
        if q.key == "breached":
            cls = cls + " alert"
        aria = ""
        if current is not None and q.key == current:
            aria = ' aria-current="page"'
        links.append(
            '<a class="' + cls + '" href="/?q=' + key + '" hx-get="/?q=' + key + '"'
            ' hx-target="#content" hx-push-url="true"' + aria + ">"
            "<span>" + esc(q.label) + "</span>"
            '<span class="count">' + str(len(q.case_ids)) + "</span></a>"
        )

    options = []
    anon_sel = ""
    if me.role == "anonymous":
        anon_sel = " selected"
    options.append('<option value=""' + anon_sel + ">anonymous</option>")
    for p in desk.people():
        if p.role == "anonymous":
            continue
        sel = ""
        if me.role != "anonymous" and p.name == me.name:
            sel = " selected"
        options.append('<option value="' + esc(p.name) + '"' + sel + ">" + _person_label(p, esc) + "</option>")

    oob_attr = ""
    if oob:
        oob_attr = ' hx-swap-oob="true"'

    return (
        '<aside id="sidebar" class="sidebar"' + oob_attr + ">"
        '<div class="brand">Relay<span>.</span></div>'
        '<nav class="nav">' + "".join(links) + "</nav>"
        '<button type="button" class="btn-new" hx-get="/new" hx-target="#content" hx-push-url="true">+ New case</button>'
        '<form class="persona" method="post" action="/persona" hx-post="/persona" hx-trigger="change" hx-target="#content">'
        '<label for="persona-select">Viewing as</label>'
        '<select id="persona-select" name="persona">'
        + "".join(options)
        + "</select>"
        "<noscript><button type=\"submit\" class=\"btn btn-small\">Switch</button></noscript>"
        "</form>"
        '<div class="deskdate">Desk date ' + esc(str(desk.today())) + "</div>"
        "</aside>"
    )
