package main

import (
	"fmt"
	"net/http"

	"backend/config"
	"backend/handlers"

	"github.com/gin-gonic/gin"
)

func main() {
	config.InitDB()
	config.InitRabbitMQ()
	config.InitMinio()

	defer config.RabbitConn.Close()
	defer config.RabbitChannel.Close()

	router := gin.Default()
	router.MaxMultipartMemory = 8 << 20 // 8 MB
	router.LoadHTMLGlob("templates/*")

	router.GET("/", func(c *gin.Context) {
		c.HTML(http.StatusOK, "index.html", nil)
	})

	api := router.Group("/api")
	{
		api.POST("/upload", handlers.UploadDocument)
		api.GET("/status/:id", handlers.CheckStatus)
		api.GET("/image/:id", handlers.GetDocumentImage)
		api.GET("/documents", handlers.GetAllDocuments)
		api.POST("/internal/complete", handlers.CompleteDocument)
	}

	fmt.Println("[*] Go-сервер запущен на http://localhost:8080")
	router.Run(":8080")
}