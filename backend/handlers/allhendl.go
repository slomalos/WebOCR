package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"path/filepath"
	"time"

	"backend/config"
	"backend/models"

	"github.com/gin-gonic/gin"
	"github.com/minio/minio-go/v7"
	amqp "github.com/rabbitmq/amqp091-go"
)

func UploadDocument(c *gin.Context) {
	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Файл не найден"})
		return
	}

	filename := fmt.Sprintf("%d_%s", time.Now().Unix(), filepath.Base(file.Filename))
	bucketName := "scans"

	fileContent, err := file.Open()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Не удалось открыть файл"})
		return
	}
	defer fileContent.Close()

	_, err = config.MinioClient.PutObject(context.Background(), bucketName, filename, fileContent, file.Size, minio.PutObjectOptions{ContentType: file.Header.Get("Content-Type")})
	if err != nil {
		fmt.Println("[!] Ошибка MinIO PutObject:", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Ошибка загрузки в Minio"})
		return
	}

	storagePath := fmt.Sprintf("%s/%s", bucketName, filename)
	doc := models.Document{
		OriginalName: file.Filename,
		StorageURL:   storagePath,
		Status:       "PENDING",
	}
	config.DB.Create(&doc)

	taskMsg := map[string]interface{}{
		"document_id": doc.ID,
		"file_path":   storagePath,
	}
	body, _ := json.Marshal(taskMsg)

	err = config.RabbitChannel.Publish("", "ocr_tasks", false, false, amqp.Publishing{
		ContentType: "application/json",
		Body:        body,
	})
	if err != nil {
    	fmt.Println("[!] Ошибка RabbitMQ Publish:", err)
    }

	c.JSON(http.StatusOK, gin.H{
		"message":     "Файл загружен в S3 и отправлен в очередь",
		"document_id": doc.ID,
	})
}

func CheckStatus(c *gin.Context) {
	docID := c.Param("id")
	var doc models.Document
	if err := config.DB.First(&doc, docID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Документ не найден"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"status": doc.Status, "text": doc.ParsedText})
}

func CompleteDocument(c *gin.Context) {
	var req models.CompleteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Неверный формат данных"})
		return
	}

	result := config.DB.Model(&models.Document{}).Where("id = ?", req.DocumentID).Updates(map[string]interface{}{
		"status":      "SUCCESS",
		"parsed_text": req.ParsedText,
		"storage_url": req.NewStorageURL,
	})

	if result.Error != nil || result.RowsAffected == 0 {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Документ не обновлен"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Результат успешно сохранен"})
}

func GetDocumentImage(c *gin.Context) {
	docID := c.Param("id")
	var doc models.Document

	if err := config.DB.First(&doc, docID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Документ не найден"})
		return
	}

	bucketName := "scans"
	objectName := doc.StorageURL[len(bucketName)+1:]

	object, err := config.MinioClient.GetObject(context.Background(), bucketName, objectName, minio.GetObjectOptions{})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Файл не найден в хранилище"})
		return
	}
	defer object.Close()

	io.Copy(c.Writer, object)
}

func GetAllDocuments(c *gin.Context) {
	var docs []models.Document
	if err := config.DB.Order("id desc").Find(&docs).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Не удалось получить историю"})
		return
	}
	c.JSON(http.StatusOK, docs)
}