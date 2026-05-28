package config

import (
	"fmt"
	"log"

	"backend/models"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

var DB *gorm.DB

func InitDB() {
	dsn := "host=localhost user=ege_user password=ege_password dbname=ege_db port=5432 sslmode=disable"
	var err error
	DB, err = gorm.Open(postgres.Open(dsn), &gorm.Config{})
	if err != nil {
		log.Fatal("[!] Ошибка БД: ", err)
	}
	DB.AutoMigrate(&models.Document{})
	fmt.Println("[*] Подключение к PostgreSQL успешно!")
}