package config

import (
	"fmt"
	"log"

	"backend/models"
	"os"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

var DB *gorm.DB

func InitDB() {
	host := os.Getenv("DB_HOST")
		if host == "" {
		host = "localhost"
	}
	dsn := fmt.Sprintf("host=%s user=ege_user password=ege_password dbname=ege_db port=5432 sslmode=disable", host)
	var err error
	DB, err = gorm.Open(postgres.Open(dsn), &gorm.Config{})
	if err != nil {
		log.Fatal("[!] Ошибка БД: ", err)
	}
	DB.AutoMigrate(&models.Document{})
	fmt.Println("[*] Подключение к PostgreSQL успешно!")
}