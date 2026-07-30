// demo/main.go
//
// Small runnable Go program embedding the Dafny-verified authorization
// kernel (compiled from authz.dfy via `dafny build --target:go`).
//
// This program does NOT re-test the ten rules — that would just be
// rung-2/3 testing bolted onto a proof that already covers all inputs.
// It demonstrates that the *compiled* kernel is usable from ordinary Go
// code and spot-checks a handful of scenarios called out in the task,
// including two edge cases the rules are specifically about (deactivated
// staff, anonymous drafts) and a "feature" case (active editor can see a
// draft) to show the kernel isn't a bug-for-bug "always deny" stub.
package main

import (
	"fmt"
	"os"

	m_Authz "Authz"
)

type scenario struct {
	name     string
	role     m_Authz.Role
	isAuthor bool
	active   bool
	state    m_Authz.ArticleState
	wantView bool
	wantEdit bool
	wantPubl bool
}

func roleName(r m_Authz.Role) string {
	switch {
	case r.Is_Anonymous():
		return "anonymous"
	case r.Is_Author():
		return "author"
	case r.Is_Editor():
		return "editor"
	case r.Is_Admin():
		return "admin"
	}
	return "?"
}

func stateName(s m_Authz.ArticleState) string {
	switch {
	case s.Is_Draft():
		return "draft"
	case s.Is_InReview():
		return "in_review"
	case s.Is_Published():
		return "published"
	case s.Is_Archived():
		return "archived"
	}
	return "?"
}

func b(x bool) string {
	if x {
		return "yes"
	}
	return "no"
}

func main() {
	C := m_Authz.Companion_Role_
	S := m_Authz.Companion_ArticleState_

	scenarios := []scenario{
		// --- Task-mandated scenarios ---
		{
			name: "deactivated editor, publish in_review article",
			role: C.Create_Editor_(), isAuthor: false, active: false, state: S.Create_InReview_(),
			// inv_deactivated_does_nothing only restricts edit/publish, not view —
			// a deactivated editor can still SEE an in_review article as staff, but
			// cannot edit or (the scenario under test) publish it.
			wantView: true, wantEdit: false, wantPubl: false,
		},
		{
			name: "anonymous visitor, view a draft",
			role: C.Create_Anonymous_(), isAuthor: false, active: true, state: S.Create_Draft_(),
			wantView: false, wantEdit: false, wantPubl: false, // inv_draft_visibility / inv_anonymous_published_only
		},
		{
			name: "active editor, view a draft",
			role: C.Create_Editor_(), isAuthor: false, active: true, state: S.Create_Draft_(),
			wantView: true, wantEdit: true, wantPubl: false, // FEATURE: staff can see + edit drafts
		},

		// --- Additional coverage over the remaining rules ---
		{
			name: "anonymous visitor, view a published article",
			role: C.Create_Anonymous_(), isAuthor: false, active: true, state: S.Create_Published_(),
			wantView: true, wantEdit: false, wantPubl: false, // inv_published_is_public
		},
		{
			name: "anonymous visitor, view an archived article",
			role: C.Create_Anonymous_(), isAuthor: false, active: true, state: S.Create_Archived_(),
			wantView: false, wantEdit: false, wantPubl: false, // inv_archived_not_public
		},
		{
			name: "admin, view an archived article",
			role: C.Create_Admin_(), isAuthor: false, active: true, state: S.Create_Archived_(),
			wantView: true, wantEdit: true, wantPubl: false, // staff reference access
		},
		{
			name: "author, edit own draft",
			role: C.Create_Author_(), isAuthor: true, active: true, state: S.Create_Draft_(),
			wantView: true, wantEdit: true, wantPubl: false, // FEATURE: authors can edit their own drafts
		},
		{
			name: "author, edit own PUBLISHED article",
			role: C.Create_Author_(), isAuthor: true, active: true, state: S.Create_Published_(),
			wantView: true, wantEdit: false, wantPubl: false, // inv_authors_edit_unpublished_only
		},
		{
			name: "author, try to publish own in_review article",
			role: C.Create_Author_(), isAuthor: true, active: true, state: S.Create_InReview_(),
			wantView: true, wantEdit: true, wantPubl: false, // inv_publish_staff_only
		},
		{
			name: "active editor, try to publish a DRAFT (not in_review)",
			role: C.Create_Editor_(), isAuthor: false, active: true, state: S.Create_Draft_(),
			wantView: true, wantEdit: true, wantPubl: false, // inv_publish_from_review_only
		},
		{
			name: "active editor, publish in_review article",
			role: C.Create_Editor_(), isAuthor: false, active: true, state: S.Create_InReview_(),
			wantView: true, wantEdit: true, wantPubl: true, // FEATURE: staff can actually publish
		},
		{
			name: "deactivated author, view own draft",
			role: C.Create_Author_(), isAuthor: true, active: false, state: S.Create_Draft_(),
			// view is not gated on `active` by the YAML rules (only edit/publish are:
			// inv_deactivated_does_nothing says nothing about can_view) — the kernel
			// still lets a deactivated author see their own unpublished draft, but
			// never edit or publish it.
			wantView: true, wantEdit: false, wantPubl: false,
		},
	}

	fmt.Println("Dafny-verified CMS authorization kernel — demo")
	fmt.Println(strRepeat("=", 100))
	fmt.Printf("%-46s %-8s %-8s %-8s\n", "scenario", "view", "edit", "publish")
	fmt.Println(strRepeat("-", 100))

	failures := 0
	for _, sc := range scenarios {
		got := m_Authz.Companion_Default___.Authorize(sc.role, sc.isAuthor, sc.active, sc.state)
		gv, ge, gp := got.Dtor_view(), got.Dtor_edit(), got.Dtor_publish()

		ok := gv == sc.wantView && ge == sc.wantEdit && gp == sc.wantPubl
		mark := "OK"
		if !ok {
			mark = "MISMATCH"
			failures++
		}

		fmt.Printf("%-46s %-8s %-8s %-8s  [%s]\n",
			sc.name, mark2(gv, sc.wantView), mark2(ge, sc.wantEdit), mark2(gp, sc.wantPubl), mark)
		_ = roleName
		_ = stateName
		_ = b
	}

	fmt.Println(strRepeat("=", 100))
	if failures > 0 {
		fmt.Printf("%d scenario(s) FAILED (kernel output disagreed with expectation)\n", failures)
		os.Exit(1)
	}
	fmt.Println("All scenarios matched. (Recall: the ten YAML rules were proved for ALL inputs by")
	fmt.Println("`dafny verify` before this program was ever built — this table is a sanity spot")
	fmt.Println("check of the compiled artifact, not the source of assurance.)")
}

func mark2(got, want bool) string {
	if got == want {
		return b(got)
	}
	return b(got) + "!="
}

func strRepeat(s string, n int) string {
	out := make([]byte, 0, n)
	for i := 0; i < n; i++ {
		out = append(out, s[0])
	}
	return string(out)
}
