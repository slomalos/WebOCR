package models

import (
	"time"

	"gorm.io/gorm"
)

type Document struct {
	ID           uint           `gorm:"primaryKey;autoIncrement" json:"id"`
	OriginalName string         `gorm:"type:varchar(255);not null" json:"original_name"`
	StorageURL   string         `gorm:"type:varchar(500);not null" json:"storage_url"`
	Status       string         `gorm:"type:varchar(50);default:'PENDING'" json:"status"`
	ParsedText   string         `gorm:"type:text" json:"parsed_text"`
	CreatedAt    time.Time      `json:"created_at"`
	UpdatedAt    time.Time      `json:"updated_at"`
	DeletedAt    gorm.DeletedAt `gorm:"index" json:"-"`
}

type CompleteRequest struct {
	DocumentID    uint   `json:"document_id"`
	ParsedText    string `json:"parsed_text"`
	NewStorageURL string `json:"new_storage_url"`
}