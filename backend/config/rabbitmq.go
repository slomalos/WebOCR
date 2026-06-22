package config

import (
	"fmt"
	"log"
	"os"

	amqp "github.com/rabbitmq/amqp091-go"
)

var RabbitConn *amqp.Connection
var RabbitChannel *amqp.Channel

func InitRabbitMQ() {
	var err error
		host := os.Getenv("RABBITMQ_HOST")
	if host == "" {
		host = "localhost"
	}
	url := fmt.Sprintf("amqp://guest:guest@%s:5672/", host)
	RabbitConn, err = amqp.Dial(url)
	if err != nil {
		log.Fatal("[!] Ошибка RabbitMQ: ", err)
	}
	RabbitChannel, err = RabbitConn.Channel()
	if err != nil {
		log.Fatal("[!] Ошибка канала RabbitMQ: ", err)
	}
	_, err = RabbitChannel.QueueDeclare("ocr_tasks", true, false, false, false, nil)
	if err != nil {
		log.Fatal("[!] Ошибка очереди: ", err)
	}
	fmt.Println("[*] Подключение к RabbitMQ успешно!")
}