package auth

import (
    "github.com/gin-gonic/gin"
)

type User struct {
    ID       string                 `json:"id"`
    Email    string                 `json:"email"`
    Name     string                 `json:"name"`
    Groups   []string               `json:"groups"`
    Metadata map[string]interface{} `json:"metadata"`
}

type Provider interface {
    LoginHandler() gin.HandlerFunc
    CallbackHandler() gin.HandlerFunc
    LogoutHandler() gin.HandlerFunc
    ValidateToken(token string) (*User, error)
    GetUser(ctx *gin.Context) (*User, error)
}