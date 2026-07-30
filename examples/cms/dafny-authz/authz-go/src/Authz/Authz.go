// Package Authz
// Dafny module Authz compiled into Go

package Authz

import (
	m__System "System_"
	_dafny "dafny"
	os "os"
)

var _ = os.Args
var _ _dafny.Dummy__
var _ m__System.Dummy__

type Dummy__ struct{}

// Definition of class Default__
type Default__ struct {
	dummy byte
}

func New_Default___() *Default__ {
	_this := Default__{}

	return &_this
}

type CompanionStruct_Default___ struct {
}

var Companion_Default___ = CompanionStruct_Default___{}

func (_this *Default__) Equals(other *Default__) bool {
	return _this == other
}

func (_this *Default__) EqualsGeneric(x interface{}) bool {
	other, ok := x.(*Default__)
	return ok && _this.Equals(other)
}

func (*Default__) String() string {
	return "Authz.Default__"
}
func (_this *Default__) ParentTraits_() []*_dafny.TraitID {
	return [](*_dafny.TraitID){}
}

var _ _dafny.TraitOffspring = &Default__{}

func (_static *CompanionStruct_Default___) Authorize(role Role, isAuthor bool, active bool, state ArticleState) Decision {
	var _0_view bool = (func() bool {
		if (state).Equals(Companion_ArticleState_.Create_Published_()) {
			return true
		}
		return (func() bool {
			if (state).Equals(Companion_ArticleState_.Create_Archived_()) {
				return !(role).Equals(Companion_Role_.Create_Anonymous_())
			}
			return (func() bool {
				if ((state).Equals(Companion_ArticleState_.Create_Draft_())) || ((state).Equals(Companion_ArticleState_.Create_InReview_())) {
					return ((isAuthor) || ((role).Equals(Companion_Role_.Create_Editor_()))) || ((role).Equals(Companion_Role_.Create_Admin_()))
				}
				return false
			})()
		})()
	})()
	_ = _0_view
	var _1_edit bool = (func() bool {
		if !(active) {
			return false
		}
		return (func() bool {
			if ((role).Equals(Companion_Role_.Create_Editor_())) || ((role).Equals(Companion_Role_.Create_Admin_())) {
				return true
			}
			return (func() bool {
				if ((role).Equals(Companion_Role_.Create_Author_())) && (isAuthor) {
					return ((state).Equals(Companion_ArticleState_.Create_Draft_())) || ((state).Equals(Companion_ArticleState_.Create_InReview_()))
				}
				return false
			})()
		})()
	})()
	_ = _1_edit
	var _2_publish bool = (func() bool {
		if !(active) {
			return false
		}
		return (func() bool {
			if ((role).Equals(Companion_Role_.Create_Editor_())) || ((role).Equals(Companion_Role_.Create_Admin_())) {
				return (state).Equals(Companion_ArticleState_.Create_InReview_())
			}
			return false
		})()
	})()
	_ = _2_publish
	return Companion_Decision_.Create_Decision_(_0_view, _1_edit, _2_publish)
}

// End of class Default__

// Definition of datatype Role
type Role struct {
	Data_Role_
}

func (_this Role) Get_() Data_Role_ {
	return _this.Data_Role_
}

type Data_Role_ interface {
	isRole()
}

type CompanionStruct_Role_ struct {
}

var Companion_Role_ = CompanionStruct_Role_{}

type Role_Anonymous struct {
}

func (Role_Anonymous) isRole() {}

func (CompanionStruct_Role_) Create_Anonymous_() Role {
	return Role{Role_Anonymous{}}
}

func (_this Role) Is_Anonymous() bool {
	_, ok := _this.Get_().(Role_Anonymous)
	return ok
}

type Role_Author struct {
}

func (Role_Author) isRole() {}

func (CompanionStruct_Role_) Create_Author_() Role {
	return Role{Role_Author{}}
}

func (_this Role) Is_Author() bool {
	_, ok := _this.Get_().(Role_Author)
	return ok
}

type Role_Editor struct {
}

func (Role_Editor) isRole() {}

func (CompanionStruct_Role_) Create_Editor_() Role {
	return Role{Role_Editor{}}
}

func (_this Role) Is_Editor() bool {
	_, ok := _this.Get_().(Role_Editor)
	return ok
}

type Role_Admin struct {
}

func (Role_Admin) isRole() {}

func (CompanionStruct_Role_) Create_Admin_() Role {
	return Role{Role_Admin{}}
}

func (_this Role) Is_Admin() bool {
	_, ok := _this.Get_().(Role_Admin)
	return ok
}

func (CompanionStruct_Role_) Default() Role {
	return Companion_Role_.Create_Anonymous_()
}

func (_ CompanionStruct_Role_) AllSingletonConstructors() _dafny.Iterator {
	i := -1
	return func() (interface{}, bool) {
		i++
		switch i {
		case 0:
			return Companion_Role_.Create_Anonymous_(), true
		case 1:
			return Companion_Role_.Create_Author_(), true
		case 2:
			return Companion_Role_.Create_Editor_(), true
		case 3:
			return Companion_Role_.Create_Admin_(), true
		default:
			return Role{}, false
		}
	}
}

func (_this Role) String() string {
	switch _this.Get_().(type) {
	case nil:
		return "null"
	case Role_Anonymous:
		{
			return "Authz.Role.Anonymous"
		}
	case Role_Author:
		{
			return "Authz.Role.Author"
		}
	case Role_Editor:
		{
			return "Authz.Role.Editor"
		}
	case Role_Admin:
		{
			return "Authz.Role.Admin"
		}
	default:
		{
			return "<unexpected>"
		}
	}
}

func (_this Role) Equals(other Role) bool {
	switch _this.Get_().(type) {
	case Role_Anonymous:
		{
			_, ok := other.Get_().(Role_Anonymous)
			return ok
		}
	case Role_Author:
		{
			_, ok := other.Get_().(Role_Author)
			return ok
		}
	case Role_Editor:
		{
			_, ok := other.Get_().(Role_Editor)
			return ok
		}
	case Role_Admin:
		{
			_, ok := other.Get_().(Role_Admin)
			return ok
		}
	default:
		{
			return false // unexpected
		}
	}
}

func (_this Role) EqualsGeneric(other interface{}) bool {
	typed, ok := other.(Role)
	return ok && _this.Equals(typed)
}

func Type_Role_() _dafny.TypeDescriptor {
	return type_Role_{}
}

type type_Role_ struct {
}

func (_this type_Role_) Default() interface{} {
	return Companion_Role_.Default()
}

func (_this type_Role_) String() string {
	return "Authz.Role"
}
func (_this Role) ParentTraits_() []*_dafny.TraitID {
	return [](*_dafny.TraitID){}
}

var _ _dafny.TraitOffspring = Role{}

// End of datatype Role

// Definition of datatype ArticleState
type ArticleState struct {
	Data_ArticleState_
}

func (_this ArticleState) Get_() Data_ArticleState_ {
	return _this.Data_ArticleState_
}

type Data_ArticleState_ interface {
	isArticleState()
}

type CompanionStruct_ArticleState_ struct {
}

var Companion_ArticleState_ = CompanionStruct_ArticleState_{}

type ArticleState_Draft struct {
}

func (ArticleState_Draft) isArticleState() {}

func (CompanionStruct_ArticleState_) Create_Draft_() ArticleState {
	return ArticleState{ArticleState_Draft{}}
}

func (_this ArticleState) Is_Draft() bool {
	_, ok := _this.Get_().(ArticleState_Draft)
	return ok
}

type ArticleState_InReview struct {
}

func (ArticleState_InReview) isArticleState() {}

func (CompanionStruct_ArticleState_) Create_InReview_() ArticleState {
	return ArticleState{ArticleState_InReview{}}
}

func (_this ArticleState) Is_InReview() bool {
	_, ok := _this.Get_().(ArticleState_InReview)
	return ok
}

type ArticleState_Published struct {
}

func (ArticleState_Published) isArticleState() {}

func (CompanionStruct_ArticleState_) Create_Published_() ArticleState {
	return ArticleState{ArticleState_Published{}}
}

func (_this ArticleState) Is_Published() bool {
	_, ok := _this.Get_().(ArticleState_Published)
	return ok
}

type ArticleState_Archived struct {
}

func (ArticleState_Archived) isArticleState() {}

func (CompanionStruct_ArticleState_) Create_Archived_() ArticleState {
	return ArticleState{ArticleState_Archived{}}
}

func (_this ArticleState) Is_Archived() bool {
	_, ok := _this.Get_().(ArticleState_Archived)
	return ok
}

func (CompanionStruct_ArticleState_) Default() ArticleState {
	return Companion_ArticleState_.Create_Draft_()
}

func (_ CompanionStruct_ArticleState_) AllSingletonConstructors() _dafny.Iterator {
	i := -1
	return func() (interface{}, bool) {
		i++
		switch i {
		case 0:
			return Companion_ArticleState_.Create_Draft_(), true
		case 1:
			return Companion_ArticleState_.Create_InReview_(), true
		case 2:
			return Companion_ArticleState_.Create_Published_(), true
		case 3:
			return Companion_ArticleState_.Create_Archived_(), true
		default:
			return ArticleState{}, false
		}
	}
}

func (_this ArticleState) String() string {
	switch _this.Get_().(type) {
	case nil:
		return "null"
	case ArticleState_Draft:
		{
			return "Authz.ArticleState.Draft"
		}
	case ArticleState_InReview:
		{
			return "Authz.ArticleState.InReview"
		}
	case ArticleState_Published:
		{
			return "Authz.ArticleState.Published"
		}
	case ArticleState_Archived:
		{
			return "Authz.ArticleState.Archived"
		}
	default:
		{
			return "<unexpected>"
		}
	}
}

func (_this ArticleState) Equals(other ArticleState) bool {
	switch _this.Get_().(type) {
	case ArticleState_Draft:
		{
			_, ok := other.Get_().(ArticleState_Draft)
			return ok
		}
	case ArticleState_InReview:
		{
			_, ok := other.Get_().(ArticleState_InReview)
			return ok
		}
	case ArticleState_Published:
		{
			_, ok := other.Get_().(ArticleState_Published)
			return ok
		}
	case ArticleState_Archived:
		{
			_, ok := other.Get_().(ArticleState_Archived)
			return ok
		}
	default:
		{
			return false // unexpected
		}
	}
}

func (_this ArticleState) EqualsGeneric(other interface{}) bool {
	typed, ok := other.(ArticleState)
	return ok && _this.Equals(typed)
}

func Type_ArticleState_() _dafny.TypeDescriptor {
	return type_ArticleState_{}
}

type type_ArticleState_ struct {
}

func (_this type_ArticleState_) Default() interface{} {
	return Companion_ArticleState_.Default()
}

func (_this type_ArticleState_) String() string {
	return "Authz.ArticleState"
}
func (_this ArticleState) ParentTraits_() []*_dafny.TraitID {
	return [](*_dafny.TraitID){}
}

var _ _dafny.TraitOffspring = ArticleState{}

// End of datatype ArticleState

// Definition of datatype Decision
type Decision struct {
	Data_Decision_
}

func (_this Decision) Get_() Data_Decision_ {
	return _this.Data_Decision_
}

type Data_Decision_ interface {
	isDecision()
}

type CompanionStruct_Decision_ struct {
}

var Companion_Decision_ = CompanionStruct_Decision_{}

type Decision_Decision struct {
	View    bool
	Edit    bool
	Publish bool
}

func (Decision_Decision) isDecision() {}

func (CompanionStruct_Decision_) Create_Decision_(View bool, Edit bool, Publish bool) Decision {
	return Decision{Decision_Decision{View, Edit, Publish}}
}

func (_this Decision) Is_Decision() bool {
	_, ok := _this.Get_().(Decision_Decision)
	return ok
}

func (CompanionStruct_Decision_) Default() Decision {
	return Companion_Decision_.Create_Decision_(false, false, false)
}

func (_this Decision) Dtor_view() bool {
	return _this.Get_().(Decision_Decision).View
}

func (_this Decision) Dtor_edit() bool {
	return _this.Get_().(Decision_Decision).Edit
}

func (_this Decision) Dtor_publish() bool {
	return _this.Get_().(Decision_Decision).Publish
}

func (_this Decision) String() string {
	switch data := _this.Get_().(type) {
	case nil:
		return "null"
	case Decision_Decision:
		{
			return "Authz.Decision.Decision" + "(" + _dafny.String(data.View) + ", " + _dafny.String(data.Edit) + ", " + _dafny.String(data.Publish) + ")"
		}
	default:
		{
			return "<unexpected>"
		}
	}
}

func (_this Decision) Equals(other Decision) bool {
	switch data1 := _this.Get_().(type) {
	case Decision_Decision:
		{
			data2, ok := other.Get_().(Decision_Decision)
			return ok && data1.View == data2.View && data1.Edit == data2.Edit && data1.Publish == data2.Publish
		}
	default:
		{
			return false // unexpected
		}
	}
}

func (_this Decision) EqualsGeneric(other interface{}) bool {
	typed, ok := other.(Decision)
	return ok && _this.Equals(typed)
}

func Type_Decision_() _dafny.TypeDescriptor {
	return type_Decision_{}
}

type type_Decision_ struct {
}

func (_this type_Decision_) Default() interface{} {
	return Companion_Decision_.Default()
}

func (_this type_Decision_) String() string {
	return "Authz.Decision"
}
func (_this Decision) ParentTraits_() []*_dafny.TraitID {
	return [](*_dafny.TraitID){}
}

var _ _dafny.TraitOffspring = Decision{}

// End of datatype Decision
